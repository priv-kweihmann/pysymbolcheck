import argparse
import copy
import glob
import json
import os
import re
import sys

import elftools.construct.macros as macros  # noqa: I900
import elftools.elf.elffile as elffile  # noqa: I900
import elftools.elf.structs as structs  # noqa: I900
from jsonmerge import merge

symbols = {}
rules = {}
fut = None

_mapping_table = {
    r"AVAILABLE\(([A-Za-z0-9_]*)\)": r"__get_available('\1')",
    r"USED\(([A-Za-z0-9_]*)\)": r"__get_used('\1')",
    r"SIZE\(([A-Za-z0-9_]*)\)": r"__get_size('\1')",
    r"TYPE\(([A-Za-z0-9_]*),([A-Za-z0-9_]*)\)": r"__get_type('\1', '\2')",
    r"LARGEST\(\)": r"__get_largest_symbol()",
    r"\&\&": r" and ",
    r"\|\|": r" or ",
    r"\!": r" not ",
}


def __get_largest_symbol():
    global symbols
    return max([symbols[k]["size"] for k in symbols.keys()])


def __get_available(item):
    global symbols
    return item in symbols.keys()


def __get_used(item):
    global symbols
    global fut
    if item not in symbols.keys():
        return False
    return symbols[item]["file"] == fut or ("used_in" in symbols[item] and fut in symbols[item]["used_in"])


def __get_size(item):
    global symbols
    if item not in symbols or "size" not in symbols[item]:
        return ""
    if isinstance(symbols[item]["size"], str):
        return int(symbols[item]["size"])
    return symbols[item]["size"]


def __get_type(item, type_):
    global symbols
    if item not in symbols or "type" not in symbols[item]:
        return ""
    return symbols[item]["type"]


def find_lib_in_path(filename, lib_path):
    if os.path.isabs(filename):
        return filename
    for lib in lib_path:
        # Check for in root first
        if os.path.exists(lib + "/" + filename):
            return lib + "/" + filename
    for lib in lib_path:
        # lookup in subdirs
        if any(glob.glob(lib + "/**/" + filename, recursive=True)):
            return glob.glob(lib + "/**/" + filename, recursive=True)[0]
    sys.stderr.write("Can't find the needed lib {fn}\n".format(fn=filename))
    sys.exit(-1)


def get_soname(filename, lib_path):
    stream = open(find_lib_in_path(filename, lib_path), 'rb')
    f = None
    try:
        f = elffile.ELFFile(stream)
    except BaseException:
        sys.stderr.write("Can't read input file - Seems not to be an elf\n")
        sys.exit(-1)
    dynamic = f.get_section_by_name('.dynamic')
    dynstr = f.get_section_by_name('.dynstr')

    # Handle libraries built for different machine architectures:
    if f.header['e_machine'] == 'EM_X86_64':
        st = structs.Struct('Elf64_Dyn',
                            macros.ULInt64('d_tag'),
                            macros.ULInt64('d_val'))
    elif f.header['e_machine'] == 'EM_386':
        st = structs.Struct('Elf32_Dyn',
                            macros.ULInt32('d_tag'),
                            macros.ULInt32('d_val'))
    else:
        raise RuntimeError('unsupported machine architecture')
    results = []
    try:
        entsize = dynamic['sh_entsize']
        for k in range(int(dynamic['sh_size'] / entsize)):
            result = st.parse(dynamic.data()[k * entsize:(k + 1) * entsize])
            if result.d_tag == 1:
                results.append(dynstr.get_string(result.d_val))
    except (KeyError, TypeError, AttributeError):
        pass
    return results


def get_symbols(filename, lib_path):
    result = {}
    stream = open(find_lib_in_path(filename, lib_path), 'rb')
    f = None
    try:
        f = elffile.ELFFile(stream)
    except BaseException:
        sys.stderr.write("Can't read input file - Seems not to be an elf\n")
        sys.exit(-1)
    for sec in f.iter_sections():
        try:
            for sym in sec.iter_symbols():
                if not sym.name:
                    continue
                entry = {"size": sym.entry.st_size or 0,
                         "type": sym.entry.st_info.type, "file": filename, "section": sec.name}
                if sym.entry.st_shndx == 'SHN_UNDEF':
                    entry["used_in"] = [filename]
                result[sym.name] = entry
        except BaseException:
            pass
    return result


def get_symbols_rec(filename, lib_path):
    res = get_symbols(filename, lib_path)
    for lib in get_soname(filename, lib_path):
        res = merge(res, get_symbols_rec(lib, lib_path))
    return res


def report_issues(rule):
    global fut
    sys.stdout.write(f'{fut}:{rule["severity"]}:{rule["id"]}: {rule["msg"]}\n')


def parse_rules(item):
    global _mapping_table
    global fut
    org_rule = copy.deepcopy(item["rule"])
    for k, v in _mapping_table.items():
        org_rule = re.sub(k, v, org_rule)
    org_rule = re.sub(r"\s{2,}", " ", org_rule).strip()
    try:
        compile(org_rule, "pattern_test", "eval")  # noqa: DUO110
        if eval(org_rule):  # noqa: DUO104, S307
            report_issues(item)
            return False
    except Exception as e:
        sys.stderr.write(
            "Rule {rule} is not well-formed: {e}\n".format(rule=item["rule"], e=e))
        return False
    return True


def eval_rules(rules):
    return all([parse_rules(x) for x in rules])


def create_argparses():
    parser = argparse.ArgumentParser(
        description='Eval symbols of a binary against given rules')
    parser.add_argument('rules', help='Path to a rule file')
    parser.add_argument("file", help="File to parse")
    parser.add_argument('--libpath', default="",
                        help='\":\" separated path to lookup libraries')
    return parser


def get_std_lib_paths():
    output = []
    for item in ["/lib/i386-linux-gnu", "/usr/lib/i386-linux-gnu", "/usr/local/lib", "/usr/lib",
                 "/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/lib32", "/usr/lib32", "/libx32", "/usr/libx32", "/lib"]:
        if os.path.exists(item):
            output.append((item))
    return output


def main():
    global symbols
    global fut
    args = create_argparses().parse_args()
    args.libpath = [os.getcwd()] + args.libpath.split(":") + get_std_lib_paths()
    fut = args.file
    if not os.path.isfile(fut):
        sys.stderr.write("File is not a file\n")
        sys.exit(-1)
    try:
        with open(args.rules) as f:
            rules = json.load(f)
    except BaseException:
        sys.stderr.write("Can't parse rules\n")
        sys.exit(-1)

    symbols = get_symbols_rec(args.file, args.libpath)
    if not eval_rules(rules):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
