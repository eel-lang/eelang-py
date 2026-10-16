#include <Python.h>
#include <string.h>        // memchr
#include "pycore_parser.h"   // _PyParser_ASTFromString
#include "pycore_pyarena.h"  // _PyArena_New / _PyArena_Free
#include "pycore_ast.h"      // PyAST_mod2obj, mod_ty
#include "compile.h"         // Py_file_input / Py_eval_input / Py_single_input

/* Stub: myreadline.c checks for Ctrl-C via this hidden symbol. For batch
   parsing we always report "no interrupt". */
__attribute__((visibility("hidden")))
int _PyOS_InterruptOccurred(PyThreadState *tstate)
{
    (void)tstate;
    return 0;
}

static PyObject *
parse_impl(PyObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *source_obj = NULL;
    PyObject *filename = NULL;
    int mode = Py_file_input;
    static char *kwlist[] = {"source", "filename", "mode", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|Oi", kwlist,
                                     &source_obj, &filename, &mode)) {
        return NULL;
    }
    if (!PyUnicode_Check(source_obj)) {
        PyErr_SetString(PyExc_TypeError, "source must be a str");
        return NULL;
    }
    Py_ssize_t source_len = 0;
    const char *source = PyUnicode_AsUTF8AndSize(source_obj, &source_len);
    if (source == NULL) {
        return NULL;
    }
    if (memchr(source, '\0', (size_t)source_len) != NULL) {
        PyErr_SetString(PyExc_ValueError,
                        "source code string cannot contain null bytes");
        return NULL;
    }
    if (filename != NULL && !PyUnicode_Check(filename)) {
        PyErr_SetString(PyExc_TypeError, "filename must be a str");
        return NULL;
    }
    if (mode != Py_file_input && mode != Py_eval_input
            && mode != Py_single_input) {
        PyErr_SetString(PyExc_ValueError,
                        "mode must be one of 256/257/258 (single/file/eval)");
        return NULL;
    }
    if (filename == NULL) {
        filename = PyUnicode_FromString("<eel>");
        if (filename == NULL) return NULL;
    }
    else {
        Py_INCREF(filename);
    }

    /* Источник уже декодирован вызывающим (как Py_CompileString):
       IGNORE_COOKIE запрещает токенизатору повторно перекодировать буфер
       по coding-cookie — иначе не-ASCII литералы пойдёт mojibake. */
    PyCompilerFlags flags = {.cf_flags = PyCF_IGNORE_COOKIE};

    PyArena *arena = _PyArena_New();
    if (arena == NULL) {
        Py_DECREF(filename);
        return NULL;
    }

    mod_ty mod = _PyParser_ASTFromString(source, filename, mode, &flags, arena, NULL);
    Py_DECREF(filename);
    if (mod == NULL) {
        _PyArena_Free(arena);
        return NULL;
    }

    PyObject *result = PyAST_mod2obj(mod);
    _PyArena_Free(arena);
    return result;
}

static PyMethodDef parser_methods[] = {
    {"parse", (PyCFunction)parse_impl, METH_VARARGS | METH_KEYWORDS,
     "parse(source, filename=None, mode=257) -> ast.AST"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef parsermodule = {
    PyModuleDef_HEAD_INIT, "_parser", NULL, -1, parser_methods
};

PyMODINIT_FUNC
PyInit__parser(void)
{
    PyObject *m = PyModule_Create(&parsermodule);
    if (m == NULL) {
        return NULL;
    }
    /* Ensure the ast types are initialized before PyAST_mod2obj runs. */
    if (PyImport_ImportModule("ast") == NULL) {
        PyErr_Clear();
        PyErr_SetString(PyExc_ImportError,
            "eelang._parser: failed to import the stdlib 'ast' module, "
            "which is required to convert the parse tree to ast.AST objects");
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
