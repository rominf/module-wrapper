from contextlib import suppress
from enum import IntEnum
from functools import wraps
from pathlib import Path
import inspect
import sys
import types

import poetry_version


__all__ = ['wrap', '__version__']
__version__ = poetry_version.extract(source_file=__file__)
_wrapped_objs = {}


class ProxyType(IntEnum):
    MODULE = 0
    CLASS = 1
    OBJECT = 2


class ObjectType(IntEnum):
    MODULE = 0
    CLASS = 1
    FUNCTION_OR_METHOD = 2
    COROUTINE = 3
    OBJECT = 4


class Proxy:
    pass


MethodWrapper = type(''.__add__)


# A fix for https://bugs.python.org/issue35108, uses the code from inspect module of CPython standard library
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


def wrap(obj, wrapper=None, methods_to_add=(), name=None, skip=(), wrap_return_values=False, wrap_filenames=(),
         filename=None, wrapped_name_func=None):
    """
    Wrap module, class, function or another variable recursively

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
    :param Collection[str] wrap_filenames: Files to wrap
    :param Optional[str] filename: Source file of `obj`
    :param Optional[Callable[Any, str]] wrapped_name_func: Function that accepts `obj` as argument and returns the \
    name of wrapped `obj` that will be written into wrapped `obj`
    :return: Wrapped `obj`
    """
    # noinspection PyUnresolvedReferences
    class ModuleProxy(types.ModuleType, Proxy):
        # noinspection PyShadowingNames
        def __init__(self, name, doc=None):
            super().__init__(name=name, doc=doc)

    try:
        # Subclassing from obj to pass isinstance(some_object, obj) checks. If defining the class fails, it means that
        # `obj` was not a class, that means ClassProxy wouldn't be used, we can create a dummy class.
        class ClassProxy(obj, Proxy):
            @staticmethod
            def __new__(cls, *args, **kwargs):
                # noinspection PyUnresolvedReferences
                original_obj_object = cls._original_obj(*args, **kwargs)
                # noinspection PyArgumentList
                result = wrap(obj=original_obj_object,
                              wrapper=wrapper,
                              methods_to_add=methods_to_add,
                              name=name,
                              skip=skip,
                              wrap_return_values=wrap_return_values,
                              wrap_filenames=wrap_filenames,
                              filename=filename,
                              wrapped_name_func=wrapped_name_func)
                return result
    except TypeError:
        class ClassProxy(Proxy):
            pass

    class ObjectProxy(Proxy):
        pass

    # noinspection PyShadowingNames
    def get_name(*names):
        name = None
        for obj in names:
            try:
                name = obj.__name__
            except AttributeError:
                if isinstance(obj, str):
                    name = obj
            if name is not None:
                return name
        return name

    # noinspection PyShadowingNames
    def make_key(obj, wrapper, methods_to_add, name, skip, wrap_return_values, wrap_filenames, filename,
                 wrapped_name_func):
        return (id(obj), wrapper, methods_to_add, name, skip, wrap_return_values, wrap_filenames, filename,
                wrapped_name_func)

    # noinspection PyShadowingNames
    def _wrap(obj, name, members, wrapped_obj=None):
        def get_obj_type():
            if inspect.ismodule(object=obj):
                result = ObjectType.MODULE
            elif inspect.isclass(object=obj):
                result = ObjectType.CLASS
            elif (inspect.isbuiltin(object=obj) or
                  inspect.isfunction(object=obj) or
                  inspect.ismethod(object=obj) or
                  inspect.ismethoddescriptor(object=obj) or
                  isinstance(obj, MethodWrapper)):
                result = ObjectType.FUNCTION_OR_METHOD
            elif inspect.iscoroutine(object=obj):
                result = ObjectType.COROUTINE
            else:
                result = ObjectType.OBJECT
            return result

        def create_proxy(proxy_type):
            return {
                ProxyType.MODULE: ModuleProxy(name=name),
                ProxyType.CLASS: ClassProxy,
                ProxyType.OBJECT: ObjectProxy(),
            }[proxy_type]

        def add_methods():
            for method_to_add in methods_to_add:
                method_name, method = method_to_add(wrapped_obj)
                if method is not None:
                    setattr(wrapped_obj, method_name, method)

        def set_original_obj():
            with suppress(AttributeError):
                what = type if obj_type == ObjectType.CLASS else object
                what.__setattr__(wrapped_obj, wrapped_name_func(obj), obj)

        obj_type = get_obj_type()
        if wrapped_obj is None:
            if obj_type in [ObjectType.MODULE, ObjectType.CLASS]:
                wrapped_obj = create_proxy(proxy_type=ProxyType.MODULE if inspect.ismodule(obj) else ProxyType.CLASS)
            elif obj_type == ObjectType.FUNCTION_OR_METHOD:
                wrapped_obj = function_or_method_wrapper()
            elif obj_type == ObjectType.COROUTINE:
                wrapped_obj = coroutine_wrapper()
            else:
                wrapped_obj = create_proxy(proxy_type=ProxyType.OBJECT)
        key = make_key(obj=obj,
                       wrapper=wrapper,
                       methods_to_add=methods_to_add,
                       name=name,
                       skip=skip,
                       wrap_return_values=wrap_return_values,
                       wrap_filenames=wrap_filenames,
                       filename=filename,
                       wrapped_name_func=wrapped_name_func)
        _wrapped_objs[key] = wrapped_obj
        set_original_obj()
        if obj_type in [ObjectType.FUNCTION_OR_METHOD, ObjectType.COROUTINE]:
            return wrapped_obj
        add_methods()
        for attr_name, attr_value in members:
            if attr_name not in ['__class__', '__new__']:
                raises_exception = (isinstance(attr_value, tuple) and
                                    len(attr_value) > 0 and
                                    attr_value[0] == RAISES_EXCEPTION)
                if raises_exception and not obj_type == ObjectType.MODULE:
                    def raise_exception(self):
                        _ = self
                        raise attr_value[1]

                    attr_value = property(raise_exception)
                with suppress(AttributeError, TypeError):
                    # noinspection PyArgumentList
                    attr_value_new = wrap(obj=attr_value,
                                          wrapper=wrapper,
                                          methods_to_add=methods_to_add,
                                          name=get_name(attr_value, attr_name),
                                          skip=skip,
                                          wrap_return_values=wrap_return_values,
                                          wrap_filenames=wrap_filenames,
                                          filename=get_obj_file(obj=attr_value) or filename,
                                          wrapped_name_func=wrapped_name_func)
                    with suppress(Exception):
                        setattr(wrapped_obj, attr_name, attr_value_new)
        if obj_type == ObjectType.OBJECT:
            wrapped_class_name = get_name(obj.__class__)
            # noinspection PyUnusedLocal
            class_members = []
            with suppress(ModuleNotFoundError):
                class_members = getmembers(object=obj.__class__)
            _ = _wrap(obj=obj.__class__,
                      name=wrapped_class_name,
                      members=class_members,
                      wrapped_obj=wrapped_obj.__class__)
        return wrapped_obj

    def wrap_return_values_(result):
        if wrap_return_values:
            # noinspection PyArgumentList
            result = wrap(obj=result,
                          wrapper=wrapper,
                          methods_to_add=methods_to_add,
                          name=get_name(result, 'result'),
                          skip=skip,
                          wrap_return_values=wrap_return_values,
                          wrap_filenames=wrap_filenames,
                          filename=filename,
                          wrapped_name_func=wrapped_name_func)
        return result

    # noinspection PyShadowingNames
    def is_magic_name(name):
        return name.startswith('__') and name.endswith('__')

    # noinspection PyShadowingNames
    def is_magic(obj):
        return is_magic_name(name=obj.__name__)

    # noinspection PyShadowingNames
    def is_coroutine_function(obj, wrapper):
        return inspect.iscoroutinefunction(object=wrapper(obj)) and not is_magic(obj=obj)

    # noinspection PyShadowingNames
    def wrap_call_and_wrap_return_values(obj, wrapper):
        if is_coroutine_function(obj=obj, wrapper=wrapper):
            # noinspection PyShadowingNames
            @wraps(obj)
            async def wrapper(*args, **kwargs):
                return wrap_return_values_(result=await obj(*args, **kwargs))
        else:
            # noinspection PyShadowingNames
            @wraps(obj)
            def wrapper(*args, **kwargs):
                return wrap_return_values_(result=obj(*args, **kwargs))
        return wrapper

    def function_or_method_wrapper():
        # noinspection PyShadowingNames
        @wraps(obj)
        def wrapped_obj(*args, **kwargs):
            return wrapper(obj)(*args, **kwargs)

        @wraps(obj)
        def obj_with_original_obj_as_self(*args, **kwargs):
            if len(args) > 0 and isinstance(args[0], Proxy):
                # noinspection PyProtectedMember
                args = (object.__getattribute__(args[0], '_original_obj'), ) + args[1:]
            return obj(*args, **kwargs)

        if wrapper is None:
            result = obj
        elif is_magic(obj=obj):
            if obj.__name__ == '__getattribute__':
                @wraps(obj)
                def result(*args, **kwargs):
                    # If we are trying to access magic attribute, call obj with args[0]._original_obj as self,
                    # else call wrapper.
                    if is_magic_name(name=args[1]):
                        return obj_with_original_obj_as_self(*args, **kwargs)
                    else:
                        return obj(*args, **kwargs)
            else:
                result = obj_with_original_obj_as_self
        elif obj.__name__ == '__getattr__':
            @wraps(obj)
            def result(*args, **kwargs):
                return wrapper(obj(*args, **kwargs))
        else:
            result = wrapped_obj
        if wrap_return_values:
            result = wrap_call_and_wrap_return_values(obj=result, wrapper=wrapper)
        return result

    def coroutine_wrapper():
        @wraps(obj)
        async def result(*args, **kwargs):
            return await wrapper(obj)(*args, **kwargs)

        if wrap_return_values:
            result = wrap_call_and_wrap_return_values(obj=result, wrapper=wrapper)
        return result

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

    # noinspection PyShadowingNames
    def get_obj_file(obj):
        # noinspection PyShadowingNames
        def _get_obj_file(obj):
            try:
                result = (obj.__file__
                          if hasattr(obj, '__file__') else
                          sys.modules[obj.__module__].__file__
                          if hasattr(obj, '__module__') else
                          None)
            except (AttributeError, KeyError):
                result = None
            return result

        result = _get_obj_file(obj=obj)
        if result is None:
            result = _get_obj_file(obj=type(obj))
        return result

    def get_obj_library_files():
        obj_file = get_obj_file(obj=obj)
        if obj_file is not None:
            obj_file = Path(obj_file)
            if obj_file.name == '__init__.py':
                result = obj_file.parent.glob('**/*.py')
            else:
                result = [obj_file]
            result = [str(obj_file) for obj_file in result]
        else:
            result = []
        result = frozenset(result)
        return result

    methods_to_add = frozenset(methods_to_add)
    skip = frozenset(skip)
    wrap_filenames = frozenset(wrap_filenames)

    if wrapped_name_func is None:
        # noinspection PyShadowingNames
        def wrapped_name_func(obj):
            _ = obj
            return '_original_obj'

    name = get_name(name, obj)
    if name is None:
        raise ValueError("name was not passed and obj.__name__ not found")

    key = make_key(obj=obj,
                   wrapper=wrapper,
                   methods_to_add=methods_to_add,
                   name=name,
                   skip=skip,
                   wrap_return_values=wrap_return_values,
                   wrap_filenames=wrap_filenames,
                   filename=filename,
                   wrapped_name_func=wrapped_name_func)

    wrap_filenames = wrap_filenames or get_obj_library_files()
    filename = filename or get_obj_file(obj=obj)

    # noinspection PyUnusedLocal
    members = []
    with suppress(ModuleNotFoundError):
        members = getmembers(object=obj)

    try:
        already_wrapped = key in _wrapped_objs
    except TypeError:
        already_wrapped = False
    if filename not in wrap_filenames or is_in_skip():
        wrapped_obj = obj
    elif already_wrapped:
        wrapped_obj = _wrapped_objs[key]
    elif members:
        wrapped_obj = _wrap(obj=obj, name=name, members=members)
    else:
        wrapped_obj = obj
        _wrapped_objs[key] = wrapped_obj

    return wrapped_obj
