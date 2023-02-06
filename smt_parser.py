"""
This module is a smt2 parser built upon a parser combinator library present in parser_combinator.py. 


In order to keep the parser nice and readable we establish a few rules used for development outlined below:
    1. whitespace parsing pushed down the parsing stack as far as possible
    2. avoid writing complicated parsers functions, prefer the functional pmap for short parsers and prefer avoiding pmap for longer parsers
        for a pmap style parser see parse_type_builtin_bool and for the other style see parse_type_bit_vec
    3. if an operator is commonly used, feel free to add a shorthand to keep things more readable (example ws)
"""
import parser_combinator as pc
import smt
import source
import assume_prove
import re
import typing as tp


# shortand for parser that munches whitespace since we use this call a lot
ws = pc.without_ws


def parse_op() -> pc.Parser[source.Operator]:
    ps = []

    def get_ret_fn(op: source.Operator) -> tp.Callable[[str], source.Operator]:
        def fn(_: str) -> source.Operator:
            return op
        return fn

    for op, value in smt.ops_to_smt.items():
        strValue = str(value)
        fn = get_ret_fn(op)
        p = pc.pmap(ws(pc.string(strValue)), fn)
        ps.append(p)
    return pc.choice(ps)


def parse_integer() -> pc.Parser[int]:
    def to_int(s: str) -> int:
        return int(s, 10)
    return pc.pmap(ws(pc.regex(re.compile(r"[0-9]+"))), to_int)


def parse_type_bit_vec() -> pc.Parser[source.TypeBitVec]:
    def fn(s: str) -> pc.ParseResult[source.TypeBitVec]:
        maybeStart = pc.compose(ws(pc.char('(')), ws(pc.char('_')))(s)
        if isinstance(maybeStart, pc.ParseError):
            return maybeStart
        (_, s) = maybeStart

        type_symb = ws(pc.string("BitVec"))(s)
        if isinstance(type_symb, pc.ParseError):
            return type_symb
        (_, s) = type_symb

        maybeWs = pc.ws()(s)
        assert not isinstance(maybeWs, pc.ParseError)
        (_, s) = maybeWs

        maybeSz = parse_integer()(s)
        if isinstance(maybeSz, pc.ParseError):
            return maybeSz

        (sz, s) = maybeSz
        maybeEnd = ws(pc.char(')'))(s)
        if isinstance(maybeEnd, pc.ParseError):
            return maybeEnd
        (_, s) = maybeEnd
        return (source.TypeBitVec(sz), s)
    return fn


def parse_type_builtin_bool() -> pc.Parser[source.TypeBuiltin]:
    return pc.pmap(ws(pc.string(smt.BOOL)), lambda _: source.TypeBuiltin(builtin=source.Builtin.BOOL))


def parse_type_builtin_mem() -> pc.Parser[source.TypeBuiltin]:
    return pc.pmap(ws(pc.string(smt.MEM_SORT)), lambda _: source.TypeBuiltin(builtin=source.Builtin.MEM))


def parse_type_builtin() -> pc.Parser[source.TypeBuiltin]:
    return pc.choice([parse_type_builtin_mem(), parse_type_builtin_bool()])


def parse_type() -> pc.Parser[source.Type]:
    return pc.choice([
        parse_type_bit_vec(),
        parse_type_builtin(),
    ])


def parse_cmd_declare_fun() -> pc.Parser[smt.CmdDeclareFun]:
    def fn(s: str) -> pc.ParseResult[smt.CmdDeclareFun]:
        maybeStart = pc.compose(
            ws(pc.char('(')), ws(pc.string("declare-fun")))(s)
        if isinstance(maybeStart, pc.ParseError):
            return maybeStart
        (_, s) = maybeStart

        maybeIdent = parse_identifier()(s)
        if isinstance(maybeIdent, pc.ParseError):
            return maybeIdent
        (ident, s) = maybeIdent

        maybeArgs = pc.array(
            ws(pc.char('(')),
            parse_type(),
            ws(pc.char(')')),
            pc.many1(pc.choice([
                pc.space(),
                pc.tab(),
                pc.carriage_return(),
                pc.newline()
            ]))
        )(s)
        if isinstance(maybeArgs, pc.ParseError):
            return maybeArgs
        (args, s) = maybeArgs

        maybeRetSort = parse_type()(s)
        if isinstance(maybeRetSort, pc.ParseError):
            return maybeRetSort
        (ret_sort, s) = maybeRetSort

        maybeParen = ws(pc.char(')'))(s)
        if isinstance(maybeParen, pc.ParseError):
            return maybeParen
        (_, s) = maybeParen
        return (smt.CmdDeclareFun(ident, args, ret_sort), s)
    return fn


def inner_expr() -> pc.Parser[source.ExprT[assume_prove.VarName]]:
    return NotImplemented


def parse_cmd_assert() -> pc.Parser[smt.CmdAssert]:
    fn: tp.Callable[[tp.Tuple[str, source.ExprT[assume_prove.VarName]]],
                    smt.CmdAssert] = lambda x: smt.CmdAssert(x[1])
    return pc.pmap(
        pc.compose(ws(pc.string("assert")), inner_expr()),
        fn
    )


def parse_cmd_check_sat() -> pc.Parser[smt.CmdCheckSat]:
    return pc.pmap(ws(pc.string("check-sat")), lambda _: smt.CmdCheckSat())


def parse_cmd_expr() -> pc.Parser[smt.Cmd]:
    return pc.between(
        ws(pc.char('(')),
        pc.choice([
            parse_cmd_declare_fun(),
            parse_cmd_assert(),
            parse_cmd_check_sat()
        ]),
        ws(pc.char(')'))
    )


def parse_identifier() -> pc.Parser[smt.Identifier]:
    return pc.pmap(
        ws(pc.regex(
            re.compile(smt.RE_VALID_SMTLIB_SIMPLE_SYMBOL_STR)
        )),
        lambda s: smt.Identifier(s)
    )


def parse_bool() -> pc.Parser[source.ExprT[assume_prove.VarName]]:
    return pc.pmap(ws(pc.choice([pc.string("true"), pc.string("false")])), lambda x: source.expr_true if x == "true" else source.expr_false)


def parse_hex() -> pc.Parser[int]:
    def to_int(s: str) -> int:
        return int(s[2:], 16)
    return pc.pmap(ws(pc.regex(re.compile(r"#x[0-9a-fA-F]+"))), to_int)


def parse_bin() -> pc.Parser[int]:
    def to_int(s: str) -> int:
        return int(s[2:], 2)
    return pc.pmap(ws(pc.regex(re.compile(r"#b[0-1]+"))), to_int)


def parse_num(typ: source.Type) -> pc.Parser[source.ExprT[assume_prove.VarName]]:
    "only parses hex or binary strings for now"
    fn: tp.Callable[[int], source.ExprNumT] = lambda x: source.ExprNumT(
        typ=typ, num=x)
    return pc.pmap(pc.choice([parse_hex(), parse_bin()]), fn)


def parse_define_fun_model() -> pc.Parser[smt.DeclareFunModel]:
    def fn(s: str) -> pc.ParseResult[smt.DeclareFunModel]:
        maybeStart = pc.compose(
            ws(pc.char('(')), ws(pc.string("define-fun")))(s)
        if isinstance(maybeStart, pc.ParseError):
            return maybeStart
        (_, s) = maybeStart

        maybeIdent = parse_identifier()(s)
        if isinstance(maybeIdent, pc.ParseError):
            return maybeIdent
        (ident, s) = maybeIdent

        maybeArgs = pc.array(
            ws(pc.char('(')),
            parse_type(),
            ws(pc.char(')')),
            pc.many1(pc.choice([
                pc.space(),
                pc.tab(),
                pc.carriage_return(),
                pc.newline()
            ]))
        )(s)
        if isinstance(maybeArgs, pc.ParseError):
            return maybeArgs
        (args, s) = maybeArgs

        maybeRetSort = parse_type()(s)
        if isinstance(maybeRetSort, pc.ParseError):
            return maybeRetSort
        (ret_sort, s) = maybeRetSort

        maybeExpr = pc.choice([parse_bool(), parse_num(ret_sort)])(s)
        if isinstance(maybeExpr, pc.ParseError):
            return maybeExpr

        (expr, s) = maybeExpr

        maybeParen = ws(pc.char(')'))(s)
        if isinstance(maybeParen, pc.ParseError):
            return maybeParen
        (_, s) = maybeParen
        print(s)
        return (smt.DeclareFunModel(smt.CmdDeclareFun(ident, args, ret_sort), expr), s)
    return fn


def parse_all_decl_fun_models() -> pc.Parser[tp.Sequence[smt.DeclareFunModel]]:
    return pc.between(
        ws(pc.compose(pc.char('('), pc.try_and_ignore(ws(pc.string("model"))))),
        pc.many(parse_define_fun_model()),
        ws(pc.char(')')))


def parse_sat() -> pc.Parser[smt.CheckSatResult]:
    return pc.pmap(ws(pc.string("sat")), lambda _: smt.CheckSatResult.SAT)


def parse_unsat() -> pc.Parser[smt.CheckSatResult]:
    return pc.pmap(ws(pc.string("unsat")), lambda _: smt.CheckSatResult.UNSAT)


def parse_model() -> pc.Parser[smt.Model]:
    fn: tp.Callable[[tp.Tuple[list[smt.CheckSatResult], tp.Sequence[smt.DeclareFunModel]]],
                    smt.Model] = lambda x: smt.Model(x[0], x[1])
    return pc.pmap(pc.compose(
        pc.many1(pc.choice([parse_sat(), parse_unsat()])),
        parse_all_decl_fun_models()),
        fn)
