from contextlib import suppress
from functools import wraps
from pathlib import Path
import inspect
import sys
import types

from wrapt import ObjectProxy
import poetry_version
import wrapt


__all__ = ['wrap', '__version__']
__version__ = poetry_version.extract(source_file=__file__)
_wrapped_objs = {}


# noinspection PyUnresolvedReferences
class ModuleWrapper(types.ModuleType):
    pass


# noinspection PyPep8Naming
def ClassProxy(wrapped):
    # noinspection PyShadowingNames
    class ClassProxy(wrapt.CallableObjectProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(wrapped=wrapped)
            self.__wrapped__ = wrapped(*args, **kwargs)

    return ClassProxy


# A fix for https://bugs.python.org/issue35108
RAISES_EXCEPTION = object()


# noinspection PyShadowingBuiltins
def getmembers(object, predicate=None):
    """Return all members of an object as (name, value) pairs sorted by name.
    Optionally, only return members that satisfy a given predicate."""
    if inspect.isclass(object):
        mro = (object,) + inspect.getmro(object)
    else:
        mro = ()
    results = []
    processed = set()
    names = dir(object)
    # :dd any DynamicClassAttributes to the list of names if object is a class;
    # this may result in duplicate entries if, for example, a virtual
    # attribute with the same name as a DynamicClassAttribute exists
    try:
        for base in object.__bases__:
            for k, v in base.__dict__.items():
                if isinstance(v, types.DynamicClassAttribute):
                    names.append(k)
    except AttributeError:
        pass
    for key in names:
        # First try to get the value via getattr.  Some descriptors don't
        # like calling their __get__ (see bug #1785), so fall back to
        # looking in the __dict__.
        try:
            value = getattr(object, key)
            # handle the duplicate key
            if key in processed:
                raise AttributeError
        except AttributeError:
            for base in mro:
                if key in base.__dict__:
                    value = base.__dict__[key]
                    break
            else:
                # could be a (currently) missing slot member, or a buggy
                # __dir__; discard and move on
                continue
        except Exception as e:
            value = (RAISES_EXCEPTION, e)
        if not predicate or predicate(value):
            results.append((key, value))
        processed.add(key)
    results.sort(key=lambda pair: pair[0])
    return results


def wrap(obj, wrapper=None, methods_to_add=(), name=None, skip=(), wrap_return_values=False, wrap_files=None):
    """
    Wrap module, class, function or another variable recursively (classes are wrapped using `ClassProxy` from `wrapt`
    package)

    :param Any obj: Object to wrap recursively
    :param Optional[Callable] wrapper: Wrapper to wrap functions and methods in (accepts function as argument)
    :param Collection[Callable] methods_to_add: Container of functions, which accept class as argument, and return \
    tuple of method name and method to add to all classes
    :param Optional[str] name: Name of module to wrap to (if `obj` is module)
    :param Collection[Union[str, type, Any]] skip: Items to skip wrapping (if an item of a collection is the str, wrap \
    will check the obj name, if an item of a collection is the type, wrap will check the obj type, else wrap will \
    check an item itself)
    :param bool wrap_return_values: If try, wrap return values of callables (only types, supported by wrap function \
    are supported)
    :param Collection[str] wrap_files: Files to wrap
    :return: Wrapped `obj`
    """
    # noinspection PyShadowingNames
    def get_name(*names):
        for obj in names:
            try:
                name = obj.__name__
            except AttributeError:
                name = obj
            if name:
                return name

    def add_methods():
        for method_to_add in methods_to_add:
            method_name, method = method_to_add(wrapped_obj)
            if method is not None:
                setattr(wrapped_obj, method_name, method)

    def wrap_module_or_class_or_object():
        add_methods()
        # noinspection PyUnusedLocal
        members = []
        with suppress(ModuleNotFoundError):
            members = getmembers(object=obj)
        _wrapped_objs[key] = wrapped_obj
        # noinspection PyShadowingNames
        for attr_name, attr_value in members:
            if attr_name != '__init__':
                raises_exception = (isinstance(attr_value, tuple) and
                                    len(attr_value) > 0 and
                                    attr_value[0] == RAISES_EXCEPTION)
                if raises_exception and not inspect.ismodule(object=obj):
                    def raise_exception(self):
                        _ = self
                        raise attr_value[1]

                    attr_value = property(raise_exception)
                with suppress(AttributeError, TypeError):
                    attr_value_new = wrap(obj=attr_value,
                                          wrapper=wrapper,
                                          methods_to_add=methods_to_add,
                                          name=get_name(attr_value, attr_name),
                                          skip=skip,
                                          wrap_return_values=wrap_return_values,
                                          wrap_files=wrap_files)
                    with suppress(Exception):
                        setattr(wrapped_obj, attr_name, attr_value_new)

    def wrap_return_values_(result):
        if wrap_return_values:
            # noinspection PyTypeChecker
            result = wrap(obj=result,
                          wrapper=wrapper,
                          methods_to_add=methods_to_add,
                          name=get_name(result, 'result'),
                          skip=skip,
                          wrap_return_values=wrap_return_values,
                          wrap_files=wrap_files)
            if callable(result):
                result = result()
        return result

    @wraps(obj)
    def method_wrapper(*args, **kwargs):
        is_magic = obj.__name__.startswith('__') and obj.__name__.endswith('__')
        if wrapper is None:
            result = obj(*args, **kwargs)
        elif obj.__name__ == '__getattr__':
            result = wrapper(obj(*args, **kwargs))
        elif is_magic:
            result = obj(*args, **kwargs)
        else:
            result = wrapper(obj)(*args, **kwargs)
        result = wrap_return_values_(result=result)
        return result

    @wraps(obj)
    async def coroutine_wrapper(*args, **kwargs):
        w = wrapper(obj)
        result = await w(*args, **kwargs)
        result = wrap_return_values_(result=result)
        return result

    def is_non_wrappable():
        return obj == sys or isinstance(obj, types.FrameType)

    def is_in_skip():
        result = False
        for s in skip:
            if isinstance(s, str):
                if name == s:
                    result = True
            elif isinstance(s, type):
                if isinstance(obj, s):
                    result = True
            else:
                if obj == s:
                    result = True
        return result

    def get_obj_file():
        try:
            result = (obj.__file__
                      if hasattr(obj, '__file__') else
                      sys.modules[obj.__module__].__file__
                      if hasattr(obj, '__module__') else
                      None)
        except (AttributeError, KeyError):
            result = None
        return result

    def get_obj_library_files():
        obj_file = get_obj_file()
        if obj_file is not None:
            obj_file = Path(obj_file)
            if obj_file.name == '__init__.py':
                result = obj_file.parent.glob('**/*.py')
            else:
                result = [obj_file]
            result = [str(obj_file) for obj_file in result]
        else:
            result = []
        return result

    name = get_name(name, obj)
    if name is None:
        raise ValueError("name was not passed and obj.__name__ not found")

    key = (obj, wrapper, name)

    if wrap_files is None:
        wrap_files = get_obj_library_files()

    if get_obj_file() not in wrap_files or is_non_wrappable() or is_in_skip():
        wrapped_obj = obj
    elif key in _wrapped_objs:
        wrapped_obj = _wrapped_objs[key]
    elif inspect.ismodule(obj) or inspect.isclass(obj):
        if inspect.ismodule(obj):
            wrapped_obj = ModuleWrapper(name=name)
        else:
            wrapped_obj = ClassProxy(wrapped=obj)
        wrap_module_or_class_or_object()
    elif callable(obj):
        wrapped_obj = method_wrapper
        _wrapped_objs[key] = wrapped_obj
    elif inspect.iscoroutine(object=obj):
        wrapped_obj = coroutine_wrapper
        _wrapped_objs[key] = wrapped_obj
    else:
        if getmembers(object=obj):
            wrapped_obj = ObjectProxy(wrapped=obj)
            wrap_module_or_class_or_object()
        else:
            wrapped_obj = obj
        _wrapped_objs[key] = wrapped_obj
    return wrapped_obj
