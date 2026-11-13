#!/usr/bin/env python3
"""Summarise KiCad ERC/DRC text reports.  usage: report.py <erc.rpt> <drc.rpt>"""
import collections
import re
import sys

for path in sys.argv[1:]:
    text = open(path, encoding='utf-8').read()
    kinds = collections.Counter(re.findall(r'^\[(\w+)\]', text, re.M))
    sev = collections.Counter(re.findall(r'; (error|warning)', text))
    heads = re.findall(r'^\*\* Found (\d+) (.*?) \*\*', text, re.M)
    print(f'{path}: ' + ', '.join(f'{n} {what}' for n, what in heads) + f'  ({sev.get("error", 0)} errors, {sev.get("warning", 0)} warnings)')
    for k, n in kinds.most_common():
        print(f'    {n:4d}  {k}')
