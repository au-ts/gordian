import source
import nip

conj = source.expr_and
disj = source.expr_or
imp = source.expr_implies

udiv = source.expr_udiv
mul = source.expr_mul
plus = source.expr_plus
sub = source.expr_sub
mod = source.expr_mod

slt = source.expr_slt
sle = source.expr_sle
ule = source.expr_ule
ult = source.expr_ult
eq = source.expr_eq
neq = source.expr_neq
neg = source.expr_negate

T = source.expr_true
F = source.expr_false

ite = source.expr_ite

bv8eq = source.bv8_expr_eq


u8ret = source.ExprVar(source.type_word8, source.CRetSpecialVar("c_ret.0"))
u8ret.name.field_num = 0

i32ret = source.ExprVar(source.type_word32, source.CRetSpecialVar("c_ret.0"))
i32ret.name.field_num = 0

u32ret = source.ExprVar(source.type_word32, source.CRetSpecialVar("c_ret.0"))
u32ret.name.field_num = 0


def conjs(*xs: source.ExprT[source.VarNameKind]) -> source.ExprT[source.VarNameKind]:
    # pyright is stupid, but mypy works it out (we only care about mypy)
    if len(xs) == 0:
        return T

    return source.ExprOp(source.type_bool, source.Operator.AND, xs)
    # return reduce(source.expr_and, xs)  # pyright: ignore


def ors(*xs: source.ExprT[source.VarNameKind]) -> source.ExprT[source.VarNameKind]:
    if len(xs) == 0:
        return T
    return source.ExprOp(source.type_bool, source.Operator.OR, xs)


def i32(n: int) -> source.ExprNumT:
    assert -0x8000_0000 <= n and n <= 0x7fff_ffff
    return source.ExprNum(source.type_word32, n)


def i32v(name: str) -> source.ExprVarT[source.ProgVarName]:
    # return source.ExprVar(source.type_word32, source.HumanVarName(source.HumanVarNameSubject(name), use_guard=False, path=()))
    return source.ExprVar(source.type_word32, source.ProgVarName(name + "___int#v"))


def i64v(name: str) -> source.ExprVarT[source.ProgVarName]:
    # return source.ExprVar(source.type_word64, source.HumanVarName(source.HumanVarNameSubject(name), use_guard=False, path=()))
    return source.ExprVar(source.type_word64, source.ProgVarName(name + "___long#v"))


def u32(n: int) -> source.ExprNumT:
    assert n <= 0xffff_ffff
    return source.ExprNum(source.type_word32, n)


def u32v(name: str) -> source.ExprVarT[source.ProgVarName]:
    # return source.ExprVar(source.type_word32, source.HumanVarName(source.HumanVarNameSubject(name), use_guard=False, path=()))
    return source.ExprVar(source.type_word32, source.ProgVarName(name + "___unsigned#v"))


def u64v(name: str) -> source.ExprVarT[source.ProgVarName]:
    # return source.ExprVar(source.type_word64, source.HumanVarName(source.HumanVarNameSubject(name), use_guard=False, path=()))
    return source.ExprVar(source.type_word64, source.ProgVarName(name + "___unsigned_long#v"))


def i64(n: int) -> source.ExprNumT:
    assert -0x8000_0000_0000_0000 <= n and n <= 0x7fff_ffff_ffff_ffff
    return source.ExprNum(source.type_word64, n)


def u64(n: int) -> source.ExprNumT:
    assert n <= 0xffff_ffff_ffff_ffff
    return source.ExprNum(source.type_word64, n)


def C_boolv(name: str) -> source.ExprVarT[source.ProgVarName]:
    return source.ExprVar(source.type_word8, source.ProgVarName(name + "____Bool#v"))


def g(var: source.ExprVarT[source.ProgVarName] | str) -> source.ExprVarT[nip.GuardVarName]:
    """ guard """
    if isinstance(var, str):
        return source.ExprVar(source.type_bool, nip.guard_name(source.ProgVarName(var)))
    return source.ExprVar(source.type_bool, nip.guard_name(source.ProgVarName(var.name)))


def charv(n: str) -> source.ExprVarT[source.ProgVarName]:
    return source.ExprVar(source.type_word8, source.ProgVarName(n + "___char#v"))


def ucharv(n: str) -> source.ExprVarT[source.ProgVarName]:
    return source.ExprVar(source.type_word8, source.ProgVarName(n + "___unsigned_char#v"))


def char(n: int) -> source.ExprNumT:
    return source.ExprNum(source.type_word8, n)


def sbounded(var: source.ExprVarT[source.ProgVarName], lower: source.ExprT[source.ProgVarName], upper: source.ExprT[source.ProgVarName]) -> source.ExprT[source.ProgVarName]:
    return conj(sle(lower, var), sle(var, upper))


def lh(x: str) -> source.LoopHeaderName:
    return source.LoopHeaderName(source.NodeName(x))


def arg(v: source.ExprVarT[source.ProgVarName]) -> source.ExprVarT[source.ProgVarName]:
    return source.ExprVar(v.typ, source.ProgVarName(v.name + "/arg"))


def mem_acc(ty: source.Type, v: source.ExprT[source.ProgVarName], mem: source.ExprVarT[source.ProgVarName]) -> source.ExprT[source.ProgVarName]:

    assert mem.typ == source.type_mem, "Mem typ is wrong"
    return source.ExprOp(ty, source.Operator.MEM_ACC, (mem, v, ))


def mem_upd(ty: source.Type, loc: source.ExprT[source.ProgVarName], val: source.ExprT[source.ProgVarName], mem: source.ExprT[source.ProgVarName]) -> source.ExprT[source.ProgVarName]:
    assert mem.typ == source.type_mem, "Mem typ is wrong"
    if ty != val.typ:
        print(ty, " != ", val.typ)
        print(val)
    assert ty == val.typ
    return source.ExprOp(source.type_mem, source.Operator.MEM_UPDATE, (mem, loc, val, ))


def ucast(ty: source.Type, e: source.ExprT[source.ProgVarName]) -> source.ExprT[source.ProgVarName]:
    return source.ExprOp(ty, source.Operator.WORD_CAST, (e, ))
