from enum import Enum, unique
from typing import Collection, Sequence, Tuple, Any, Dict
import argparse

import sys
import os
from typing_extensions import assert_never
from dot_graph import viz_function, viz_raw_function
import error_reporting as er
from split_prove_nodes import split_prove_nodes

import syntax
import source
import abc_cfg
import smt
import dsa
import nip
import assume_prove
import ghost_data
import ghost_code

import validate_dsa
import eval_point as ep

syntax.set_arch('rv64')


def assert_all_kernel_functions_are_reducible() -> None:
    with open('examples/kernel_CFunctions.txt') as f:
        structs, functions, const_globals = syntax.parse_and_install_all(
            f, None)
        for unsafe_func in functions.values():
            if not unsafe_func.entry:
                continue
            func = source.convert_function(
                unsafe_func)
            assert abc_cfg.is_reducible(func.cfg)
    print("[check] all kernel functions with an entry are reducible")


def same_var_diff_type(func: source.Function) -> None:
    vars: dict[str, set[source.ProgVarName]] = {}
    for n in func.nodes:
        for var in source.used_variables_in_node(func.nodes[n]).union(source.assigned_variables_in_node(func, n, with_loop_targets=True)):
            if '__' in var.name:
                real_name, type_info = var.name.split('__', maxsplit=1)

                if '.' in type_info:
                    real_name += type_info.split('.', maxsplit=1)[1]

                if real_name not in vars:
                    vars[real_name] = set()
                vars[real_name].add(var.name)

    diff = {var: uses for var, uses in vars.items() if len(uses) > 1}
    if diff:
        print(f"diffs: {func.name} {diff}")


@unique
class CmdlineOption(Enum):
    SHOW_RAW = '--show-raw'
    """ Show the raw function """

    SHOW_GRAPH = '--show-graph'
    """ Show the graph lang """

    SHOW_NIP = '--show-nip'
    """ Show the non-initialized protected cfg """

    SHOW_GHOST = '--show-ghost'
    """ Show the cfg with the ghost code inserted
        (pre condition, post condition and loop invariants)
    """

    SHOW_DSA = '--show-dsa'
    """ Show the graph after having applied dynamic single assignment """

    SHOW_AP = '--show-ap'
    """ Show the assume prove prog """

    SHOW_SMT = '--show-smt'
    """ Show the SMT given to the solvers """

    SHOW_SATS = '--show-sats'
    """ Show the raw results from the smt solvers (sat/unsat) """

    SHOW_LINE_NUMBERS = '--ln'
    """ Shows line numbers for the smt """

    SPLIT_PROVE_CONJUNCTIONS = "--split-prove-conjunctions"

    EMIT_EVALS = "--eval"

    QUIT_FAST = "--quit"


def find_functions_by_name(function_names: Collection[str], target: str) -> str:
    if target in function_names:
        return target

    for option in function_names:
        if option.endswith(target) and len(option) > len(target) and option[-len(target) - 1] == '.':
            return option

    selected: str | None = None
    for option in function_names:
        if target in option:
            if selected is None:
                selected = option
            else:
                print(
                    f"{target} doesn't allow me to chose between {selected} and {option}")
                print(f"Use a more specific name")
                exit(1)
    if selected is None:
        print(f"{target} didn't match any function name")
        print(f"The list of available functions is")
        print('\n'.join(function_names))
        exit(1)
    return selected


def run(filename: str, function_names: Collection[str], options: Collection[CmdlineOption], preludes: Sequence[str]) -> None:
    if filename.lower() == 'dsa':
        filename = 'examples/dsa.txt'
    elif filename.lower() == 'kernel':
        filename = 'examples/kernel_CFunctions.txt'
    elif filename.lower() == 'all':
        filename = 'tests/all.txt'

    if filename.endswith('.c'):
        print(
            "You probably meant to pass in the .txt file, not the .c file", file=sys.stderr)
        print("If not, don't be silly and rename it to .txt", file=sys.stderr)
        exit(1)

    if os.path.isfile(filename):
        with open(filename) as f:
            stuff = syntax.parse_and_install_all(f, None)
    else:
        print(f"filename {filename} should be the path of a file")
        exit(1)

    if len(function_names) == 0:
        print("list of functions in the file")
        for func in stuff[1].values():
            print(f'  {func.name} ({len(func.nodes)} nodes)')

    _, functions, _ = stuff

    for name in function_names:
        unsafe_func = functions[find_functions_by_name(functions.keys(), name)]
        if CmdlineOption.SHOW_RAW in options:
            viz_raw_function(unsafe_func)

        prog_func = source.convert_function(unsafe_func).with_ghost(
            ghost_data.get(filename, unsafe_func.name))
        if CmdlineOption.SHOW_GRAPH in options:
            viz_function(prog_func)

        nip_func = nip.nip(prog_func)
        if CmdlineOption.SHOW_NIP in options:
            viz_function(nip_func)

        ghost_func = ghost_code.sprinkle_ghost_code(
            filename, nip_func, functions)
        if CmdlineOption.SHOW_GHOST in options:
            viz_function(ghost_func)

        if CmdlineOption.SPLIT_PROVE_CONJUNCTIONS in options:
            ghost_func = split_prove_nodes(ghost_func)

        dsa_func = dsa.dsa(ghost_func)
        if CmdlineOption.SHOW_DSA in options:
            viz_function(dsa_func)

        extra_cmds = []
        if CmdlineOption.EMIT_EVALS in options:
            evals = ep.find_vars_for_eval(filename, name, dsa_func)
            extra_cmds = ep.make_smt_commands(evals)
        validate_dsa.validate(ghost_func, dsa_func)

        prog = assume_prove.make_prog(dsa_func)
        if CmdlineOption.SHOW_AP in options:
            assume_prove.pretty_print_prog(prog)

        smtlib = smt.make_smtlib(prog, extra_cmds, prelude_files=preludes)
        if CmdlineOption.SHOW_SMT in options:
            if CmdlineOption.SHOW_LINE_NUMBERS in options:
                lines = smtlib.splitlines()
                w = len(str(len(lines)))
                for i, line in enumerate(lines):
                    print(f'{str(i).rjust(w)}  {line}')
            else:
                print(smtlib)

        sats = tuple(smt.send_smtlib(smtlib, smt.Solver.CVC5))
        if CmdlineOption.SHOW_SATS in options:
            print(sats)
        assert len(sats) == 2
        result = smt.parse_sats(sats)
        if result is smt.VerificationResult.OK:
            print("verification succeeded", file=sys.stderr)
            exit(0)
        elif result is smt.VerificationResult.INCONSTENT:
            print("INTERNAL ERROR: smt is an inconsistent state", file=sys.stderr)
            exit(2)
        elif result is smt.VerificationResult.FAIL:
            print("verification failed (good luck figuring out why)", file=sys.stderr)
            if CmdlineOption.QUIT_FAST in options:
                exit(1)
            er.debug_func_smt(dsa_func, preludes)
            exit(1)
        else:
            assert_never(result)


def usage() -> None:
    print('usage: python3 main.py [options] <graphfile.txt> function-names...')
    print()
    print('  --show-graph: Show the graph lang')
    print('  --show-nip: Show the nip stage')
    print('  --show-ghost: Show the ghost stage')
    print('  --show-dsa: Show the graph after having applied dynamic single assignment')
    print('  --show-ap: Show the assume prove prog')
    print('  --show-smt: Show the SMT given to the solvers')
    print('  --show-sats: Show the raw results from the smt solvers (sat/unsat)')
    exit(0)


def debug1() -> None:
    with open('examples/kernel_CFunctions.txt') as f:
        structs, functions, const_globals = syntax.parse_and_install_all(
            f, None)
        pains = []
        for unsafe_func in functions.values():
            if not unsafe_func.entry:
                continue
            func = source.convert_function(
                unsafe_func)
            rets = set(var for var in func.all_variables() if var.name.startswith(
                'ret__') and '.' not in var.name and not var.name.startswith('ret___'))
            if len(rets) > 1:
                pains.append((func, unsafe_func.outputs, rets))

        for func, outputs, rets in sorted(pains, key=lambda v: len(v[0].nodes)):
            print(func.name, outputs, len(func.nodes), len(rets))


def debug() -> None:
    with open('examples/dsa.txt') as f:
        structs, functions, const_globals = syntax.parse_and_install_all(
            f, None)
        pains: list[Any] = []
        for unsafe_func in functions.values():
            if not unsafe_func.entry:
                continue
            func = source.convert_function(unsafe_func)
            ret_assigns = []
            for n in func.nodes:
                for var in source.assigned_variables_in_node(func, n, with_loop_targets=False):
                    if var.name.startswith('ret__') and not var.name.startswith('ret___'):
                        ret_assigns.append(n)
            if len(ret_assigns) > 1:
                print(func.name, ret_assigns)


def main() -> None:
    parser = argparse.ArgumentParser(
        epilog="Note: You can separate items explicitly by '--'")
    parser.add_argument("file", type=str, help="GraphLang file to use")
    parser.add_argument("fnames", default=[], nargs='*')
    parser.add_argument("-g", "--show-graph", help="Show the graph lang",
                        default=False, action="store_true")
    parser.add_argument("-n", "--show-nip", help="Show the nip stage",
                        default=False, action="store_true")
    parser.add_argument("-gh", "--show-ghost",
                        help="Show the ghost stage", default=False, action="store_true")
    parser.add_argument("-d", "--show-dsa", help="Show the graph after having applied dynamic single assignment",
                        default=False, action="store_true")
    parser.add_argument("-e", "--eval", help="Emit evaluations", default=False,
                        action="store_true")
    parser.add_argument("-q", "--quit", help="Quit fast on failure", default=False,
                        action="store_true")
    parser.add_argument("-a", "--show-ap", help="Show the assume prove prog",
                        default=False, action="store_true")
    parser.add_argument("-s", "--show-smt", help="Show the SMT given to the solvers",
                        default=False, action="store_true")
    parser.add_argument("-/", "--split-prove-conjunctions", help="split prove nodes of conjunction of n terms into n prove nodes. "
                        "Shouldn't be used when doing the final proof",
                        default=False, action="store_true")
    parser.add_argument("-r", "--show-sats", help="Show the raw results from the smt solvers",
                        default=False, action="store_true")
    parser.add_argument("-p", "--preludes", default=[], nargs="+")
    args = parser.parse_args()

    for file in args.preludes:
        if not os.path.isfile(file):
            print(f"{file} does not exist")
            exit(1)

    if not os.path.isfile(args.file):
        print(f"{args.file} is not a valid file")
        exit(1)

    if '--help' in sys.argv or '-h' in sys.argv or len(sys.argv) == 1:
        usage()

    if '--debug' in sys.argv:
        debug()
        exit(0)

    # FIXME: uh why are we doing this? just pass args straight
    options: set[CmdlineOption] = set([])
    if args.show_graph:
        options.add(CmdlineOption.SHOW_GRAPH)
    if args.show_nip:
        options.add(CmdlineOption.SHOW_NIP)
    if args.show_ghost:
        options.add(CmdlineOption.SHOW_GHOST)
    if args.show_dsa:
        options.add(CmdlineOption.SHOW_DSA)
    if args.show_ap:
        options.add(CmdlineOption.SHOW_AP)
    if args.show_smt:
        options.add(CmdlineOption.SHOW_SMT)
    if args.show_sats:
        options.add(CmdlineOption.SHOW_SATS)
    if args.split_prove_conjunctions:
        options.add(CmdlineOption.SPLIT_PROVE_CONJUNCTIONS)
    if args.eval:
        options.add(CmdlineOption.EMIT_EVALS)
    if args.quit:
        options.add(CmdlineOption.QUIT_FAST)
    run(args.file, args.fnames, options, args.preludes)


# if __name__ == "__main__":
#     main()

# print("HERE WE ARE")
main()
