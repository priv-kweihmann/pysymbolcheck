#!/usr/bin/env python3
# Copyright 2019 Konrad Weihmann
#
# Redistribution and use in source and binary forms, with or without modification, 
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, 
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, 
# this list of conditions and the following disclaimer in the documentation 
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" 
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, 
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR 
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS 
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR 
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE 
# GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) 
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, 
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE 
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Parts of this files are based on work of https://github.com/eliben/pyelftools
# licensed under public domain

import argparse
import copy
import ctypes
import glob
import json
import os
import re
import sys

try:
    import elftools
    import elftools.construct.macros as macros
    import elftools.elf.elffile as elffile
    import elftools.elf.structs as structs
except ImportError:
    print("Can't import pyelftools - Please install\nby running 'pip3 install pyelftools'")
    sys.exit(-1)
try:
    from jsonmerge import merge
except ImportError:
    print("Can't import jsonmerge - Please install\nby running 'pip3 install jsonmerge'")
    sys.exit(-1)

symbols = {}
rules = {}
fut = None

_mapping_table = {
    "AVAILABLE\(([A-Za-z0-9_]*)\)": r"__get_available('\1')",
    "USED\(([A-Za-z0-9_]*)\)": r"__get_used('\1')",
    "SIZE\(([A-Za-z0-9_]*)\)": r"__get_size('\1')",
    "TYPE\(([A-Za-z0-9_]*),([A-Za-z0-9_]*)\)": r"__get_type('\1', '\2')",
    "LARGEST\(\)": r"__get_largest_symbol()",
    "\&\&": r" and ",
    "\|\|": r" or ",
    "\!": r" not "
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
    if not item in symbols.keys():
        return False
    return symbols[item]["file"] == fut or ("used_in" in symbols[item] and fut in symbols[item]["used_in"])


def __get_size(item):
    global symbols
    if not item in symbols or not "size" in symbols[item]:
        return ""
    if isinstance(symbols[item]["size"], str):
        return int(symbols[item]["size"])
    return symbols[item]["size"]


def __get_type(item, type):
    global symbols
    if not item in symbols or not "type" in symbols[item]:
        return ""
    return symbols[item]["type"]


def find_lib_in_path(filename, lib_path):
    if os.path.isabs(filename):
        return filename
    for l in lib_path:
        # Check for in root first
        if os.path.exists(l + "/" + filename):
            return l + "/" + filename
        ## lookup in subdirs
        if any(glob.glob(l + "/**/" + filename, recursive=True)):
            return glob.glob(l + "/**/" + filename, recursive=True)[0]
    print("Can't find the needed lib {}".format(filename))
    sys.exit(-1)


def get_soname(filename, lib_path):
    stream = open(find_lib_in_path(filename, lib_path), 'rb')
    f = None
    try:
        f = elffile.ELFFile(stream)
    except:
        print("Can't read input file - Seems not to be an elf")
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
    entsize = dynamic['sh_entsize']
    for k in range(int(dynamic['sh_size']/entsize)):
        result = st.parse(dynamic.data()[k*entsize:(k+1)*entsize])
        if result.d_tag == 1:
            results.append(dynstr.get_string(result.d_val))
    return results


def get_symbols(filename, lib_path):
    result = {}
    stream = open(find_lib_in_path(filename, lib_path), 'rb')
    f = None
    try:
        f = elffile.ELFFile(stream)
    except:
        print("Can't read input file - Seems not to be an elf")
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
        except Exception as e:
            pass
    return result


def get_symbols_rec(filename, lib_path):
    res = get_symbols(filename, lib_path)
    for lib in get_soname(filename, lib_path):
        res = merge(res, get_symbols_rec(lib, lib_path))
    return res


def report_issues(rule):
    global fut
    sys.stderr.write("{}: {}: {}\n".format(fut, rule["severity"], rule["msg"]))


def parse_rules(item):
    global _mapping_table
    global fut
    org_rule = copy.deepcopy(item["rule"])
    for k, v in _mapping_table.items():
        org_rule = re.sub(k, v, org_rule)
    org_rule = re.sub(r"\s{2,}", " ", org_rule).strip()
    try:
        compile(org_rule, "pattern_test", "eval")
        if eval(org_rule):
            report_issues(item)
            return False
    except Exception as e:
        print("Rule {} is not well-formed: {}".format(item["rule"], e))
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


if __name__ == '__main__':
    args = create_argparses().parse_args()
    args.libpath = [os.getcwd()] + args.libpath.split(":")
    fut = args.file
    if not os.path.isfile(fut):
        print("File is not a file")
        sys.exit(-1)
    try:
        with open(args.rules) as f:
            rules = json.load(f)
    except:
        print("Can't parse rules")
        sys.exit(-1)

    symbols = get_symbols_rec(args.file, args.libpath)
    if not eval_rules(rules):
        sys.exit(1)
    sys.exit(0)
