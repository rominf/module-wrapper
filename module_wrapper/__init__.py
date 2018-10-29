
from contextlib import suppress
from functools import partial, wraps
import inspect
import types

from wrapt import ObjectProxy
import poetry_version
import wrapt


__all__ = ['wrap', '__version__']
__version__ = poetry_version.extract(source_file=__file__)
_wrapped_objs = {}


# noinspection PyPep8Naming
def ClassProxy(wrapped):
    # noinspection PyShadowingNames
    class ClassProxy(wrapt.CallableObjectProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(wrapped=wrapped)
            self.__wrapped__ = wrapped(*args, **kwargs)

    return ClassProxy


def wrap(obj, wrapper=None, methods_to_add=(), name=None, skip=(), wrap_return_values=False):
    """
    Wrap module, class, function or another variable recursively (classes are wrapped using `ClassProxy` from `wrapt`
    package)

    :param Any obj: Object to wrap recursively
    :param Callable wrapper: Wrapper to wrap functions and methods in (accepts function as argument)
    :param Collection[Callable] methods_to_add: Container of functions, which accept class as argument, and return \
    tuple of method name and method to add to all classes
    :param str name: Name of module to wrap to (if `obj` is module)
    :param Collection[str] skip: Items to skip wrapping
    :param bool wrap_return_values: If try, wrap return values of callables (only types, supported by wrap function \
    are supported)
    :return: Wrapped `obj`
    """
    def get_name():
        with suppress(AttributeError):
            return name or obj.__name__

    def add_methods():
        for method_to_add in methods_to_add:
            method_name, method = method_to_add(wrapped_obj)
            setattr(wrapped_obj, method_name, method)

    def wrap_module_or_class_or_object():
        add_methods()
        # noinspection PyUnusedLocal
        members = []
        with suppress(ModuleNotFoundError):
            members = inspect.getmembers(object=obj)
        _wrapped_objs[key] = wrapped_obj
        # noinspection PyShadowingNames
        for attr_name, attr_value in members:
            with suppress(AttributeError, TypeError):
                attr_value_new = wrap(obj=attr_value,
                                      wrapper=wrapper,
                                      methods_to_add=methods_to_add,
                                      name=get_name() or attr_name,
                                      skip=skip,
                                      wrap_return_values=wrap_return_values)
                setattr(wrapped_obj, attr_name, attr_value_new)

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
        if wrap_return_values:
            result = wrap(obj=result,
                          wrapper=wrapper,
                          methods_to_add=methods_to_add,
                          skip=skip,
                          wrap_return_values=wrap_return_values)
        return result

    key = (obj, wrapper, name)
    attr_name = get_name()
    if attr_name is None:
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
        else:
            wrapped_obj = ClassProxy(wrapped=obj)
        wrap_module_or_class_or_object()
    elif callable(obj):
        wrapped_obj = method_wrapper
        _wrapped_objs[key] = wrapped_obj
    else:
        if inspect.getmembers(object=obj):
            wrapped_obj = ObjectProxy(wrapped=obj)
            wrap_module_or_class_or_object()
        else:
            wrapped_obj = obj
        _wrapped_objs[key] = wrapped_obj
    return wrapped_obj
