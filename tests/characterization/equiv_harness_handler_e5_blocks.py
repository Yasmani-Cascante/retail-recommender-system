"""Extraccion de los bloques F-08C y Fase A del handler para equiv_harness_handler_e5.py (E5 nivel 2, paso 3)."""
import ast, builtins, textwrap

MARKERS = {
    "C": ("── F-08 Fase C: Diversificación visual coherente", "── Fin F-08 Fase C"),
    "A": ("── F-08 Fase A + A.5: Similitud visual en Turn 1", "── Fin F-08 Fase A+A.5"),
}

def read_source(path):
    """Lee un .py aceptando UTF-8 (con o sin BOM) y UTF-16 con BOM.

    En Windows PowerShell, `git show ... > fichero` guarda en UTF-16 y ademas
    CORROMPE los caracteres no ASCII (decodifica la salida de git con la pagina
    de codigos de la consola: 'ó' -> '├│'). La codificacion se puede tolerar;
    la corrupcion no: ver el mensaje de extract() si faltan los marcadores.
    """
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def extract(path, route):
    """Devuelve el texto de la sentencia `if (...):` del bloque, con su sangria original."""
    lines = read_source(path).replace("\r\n", "\n").split("\n")
    start_mark, end_mark = MARKERS[route]
    try:
        s = next(i for i, l in enumerate(lines) if start_mark in l)
        e = next(i for i, l in enumerate(lines) if end_mark in l)
    except StopIteration:
        raise SystemExit(
            f"No encuentro los marcadores del bloque {route} en {path}.\n"
            "Si el fichero se genero en PowerShell con `git show ... > fichero`, los\n"
            "caracteres no ASCII se corrompen (p. ej. 'ó' -> '├│') y los marcadores no\n"
            "coinciden. Generalo sin pasar por PowerShell:\n"
            '  cmd /c "git show HEAD:src/api/core/mcp_conversation_handler.py > <fichero>"'
        )
    # primera sentencia `if (` despues del marcador de inicio
    i = next(k for k in range(s, e) if lines[k].strip() == "if (")
    base = len(lines[i]) - len(lines[i].lstrip())
    # la condicion multilinea termina en la linea "):" (misma sangria que el if)
    j = next(k for k in range(i + 1, e) if lines[k].strip() == "):") + 1
    while j < e:
        l = lines[j]
        if l.strip() and not l.strip().startswith("#") and (len(l) - len(l.lstrip())) <= base:
            break
        j += 1
    return "\n".join(lines[i:j]), i + 1, j

def as_function(block_src, name="__block"):
    body = textwrap.indent(textwrap.dedent(block_src), "    ")
    return f"async def {name}():\n{body}\n    return __FALLTHROUGH__\n"

def free_names(block_src):
    fn = ast.parse(as_function(block_src))
    assigned, loaded = set(), set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            (assigned if isinstance(node.ctx, (ast.Store, ast.Del)) else loaded).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assigned.add(node.name); assigned.update(a.arg for a in node.args.args)
        elif isinstance(node, ast.alias):
            assigned.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            assigned.add(node.name)
        elif isinstance(node, (ast.comprehension,)):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name): assigned.add(t.id)
    return sorted(loaded - assigned - set(dir(builtins)) - {"__FALLTHROUGH__"})
