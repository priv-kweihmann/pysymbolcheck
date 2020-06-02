# Purpose

This tool does check compiled elf-files (and all dependencies) against given rules.
Objectives are

* check for discouraged functions (e.g. strcpy)
* check for combinations of symbols (e.g. mutex and pthreads)

## Usage

```shell
usage: pysymbolcheck [-h] [--libpath LIBPATH] rules file

Eval symbols of a binary against given rules

positional arguments:
  rules              Path to a rule file
  file               File to parse

optional arguments:
  -h, --help         show this help message and exit
  --libpath LIBPATH  ":" separated path to lookup libraries
```

## Rule file format

a rule file consists of a json-array, like this

```json
[]
```

within this __n__ element of the following can be added

```json
{ "severity": "error", "id": "A_Unique_ID", "msg": "some message", "rule", "<rule>" }
```

for __severity__ it is advised to use only **info**, **warning** or **error**

## Rule definition

A rule can consist of any logical combined operation such as

```text
((A && B) || (C && D )) && !E
```

to get the needed information following keywords are implemented

| keyword     |  variables  |                                                          purpose |            example |
| ----------- | :---------: | ---------------------------------------------------------------: | -----------------: |
| AVAILABLE() | symbol-name | check if a symbol is defined in the binary or any referenced lib | AVAILABLE(strncpy) |
| USED()      | symbol-name |                  check if a symbol is used by some binary or lib |      USED(strncpy) |
| SIZE()      | symbol-name |                                get the size in bytes of a symbol |      SIZE(strncpy) |
| TYPE()      | symbol-name |                                get the type in bytes of a symbol |      TYPE(strncpy) |
| &&          |    n.a.     |                                                      logical and |             A && B |
| \|\|        |    n.a.     |                                                       logical or |          A \|\| B  |
| !           |    n.a.     |                                                     not operator |                 !A |
