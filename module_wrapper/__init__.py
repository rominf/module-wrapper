from contextlib import suppress
from functools import partial, wraps
import inspect
import types

import wrapt


__all__ = ['wrap', '__version__']
__version__ = '0.1.0'


_wrapped_objs = {}


# noinspection PyPep8Naming
def ClassProxy(wrapped):
    # noinspection PyShadowingNames
    class ClassProxy(wrapt.CallableObjectProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(wrapped=wrapped)
            self.__wrapped__ = wrapped(*args, **kwargs)

    return ClassProxy


def wrap(obj, wrapper=None, methods_to_add=(), name=None, skip=()):
    """
    Wrap module, class, function or another variable recursively (classes are wrapped using `ClassProxy` from `wrapt`
    package)

    :param Any obj: Object to wrap recursively
    :param Callable wrapper: Wrapper to wrap functions and methods in (accepts function as argument)
    :param Collection[Callable] methods_to_add: Container of functions, which accept class as argument, and return \
    tuple of method name and method to add to all classes
    :param str name: Name of module to wrap to (if `obj` is module)
    :param Collection[str] skip: Items to skip wrapping
    :return: Wrapped `obj`
    """
    key = (obj, wrapper, name)
    try:
        attr_name = name or obj.__name__
    except AttributeError:
        raise ValueError("name was not passed and obj.__name__ not found")

    if attr_name in skip:
        wrapped_obj = obj
    elif key in _wrapped_objs:
        wrapped_obj = _wrapped_objs[key]
    elif inspect.ismodule(obj) or inspect.isclass(obj):
        if inspect.ismodule(obj):
            # noinspection PyUnresolvedReferences
            class ModuleWrapper(types.ModuleType):
                pass

            wrapped_obj = ModuleWrapper(name=attr_name)
            # noinspection PyUnusedLocal
            members = []
            with suppress(ModuleNotFoundError):
                members = inspect.getmembers(object=obj)
        else:
            wrapped_obj = ClassProxy(obj)
            members = inspect.getmembers(object=wrapped_obj)
            for method_to_add in methods_to_add:
                method_name, method = method_to_add(partial(wrapped_obj))
                setattr(wrapped_obj, method_name, method)

        _wrapped_objs[key] = wrapped_obj
        for attr_name, attr_value in members:
            with suppress(AttributeError, TypeError):
                attr_value_new = wrap(obj=attr_value, wrapper=wrapper, methods_to_add=methods_to_add, skip=skip)
                setattr(wrapped_obj, attr_name, attr_value_new)
    elif callable(obj):
        @wraps(obj)
        def method_wrapper(*args, **kwargs):
            is_magic = obj.__name__.startswith('__') and obj.__name__.endswith('__')
            if wrapper is None:
                return obj(*args, **kwargs)
            elif obj.__name__ == '__getattr__':
                return wrapper(obj(*args, **kwargs))
            elif is_magic:
                return obj(*args, **kwargs)
            else:
                return wrapper(obj)(*args, **kwargs)

        wrapped_obj = method_wrapper
        _wrapped_objs[key] = wrapped_obj
    else:
        wrapped_obj = obj
        _wrapped_objs[key] = wrapped_obj
    return wrapped_obj
