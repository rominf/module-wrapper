from contextlib import suppress
from enum import IntEnum
from functools import wraps
import inspect
import re
import stdlib_list
import types


__all__ = ['wrap', '__version__']
__version__ = "0.3.1"


STDLIB_MODULE_NAMES = stdlib_list.stdlib_list()
STDLIB_MODULE_NAMES_REGEX = f"({'|'.join(re.escape(stdlib_module_name) for stdlib_module_name in STDLIB_MODULE_NAMES)})"
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


def _wrap(
        obj,
        wrapper=None,
        methods_to_add=(),
        name=None,
        skip=(),
        wrap_return_values=False,
        wrapped_name_func=None,
        wrapped=None,
        wrapping_scope_regex=None,
):
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
    :param Optional[Callable[Any, str]] wrapped_name_func: Function that accepts `obj` as argument and returns the \
    name of wrapped `obj` that will be written into wrapped `obj`
    :param Any wrapped: Object to wrap to
    :param Optional[str] wrapping_scope_regex: regex for module names that should be wrapped
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
                result = _wrap(obj=original_obj_object,
                               wrapper=wrapper,
                               methods_to_add=methods_to_add,
                               name=name,
                               skip=skip,
                               wrap_return_values=wrap_return_values,
                               wrapped_name_func=wrapped_name_func,
                               wrapping_scope_regex=wrapping_scope_regex)
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
    def make_key(obj, wrapper, methods_to_add, name, skip, wrap_return_values, wrapped_name_func, wrapping_scope_regex):
        try:
            obj_key = 'hash', hash(obj)
        except TypeError:
            obj_key = 'id', id(obj)
        return obj_key + (
            wrapper,
            methods_to_add,
            name,
            skip,
            wrap_return_values,
            wrapped_name_func,
            wrapping_scope_regex,
        )

    # noinspection PyShadowingNames
    def wrap_(obj, name, members, wrapped=None):
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
                method_name, method = method_to_add(wrapped)
                if method is not None:
                    setattr(wrapped, method_name, method)

        def set_original_obj():
            with suppress(AttributeError):
                what = type if obj_type == ObjectType.CLASS else object
                what.__setattr__(wrapped, wrapped_name_func(obj), obj)

        def need_to_wrap():
            return not is_magic_name(name=attr_name) or attr_name not in ['__class__', '__new__']

        obj_type = get_obj_type()
        if wrapped is None:
            if obj_type in [ObjectType.MODULE, ObjectType.CLASS]:
                wrapped = create_proxy(proxy_type=ProxyType.MODULE if inspect.ismodule(obj) else ProxyType.CLASS)
            elif obj_type == ObjectType.FUNCTION_OR_METHOD:
                wrapped = function_or_method_wrapper()
            elif obj_type == ObjectType.COROUTINE:
                wrapped = coroutine_wrapper()
            else:
                wrapped = create_proxy(proxy_type=ProxyType.OBJECT)
        key = make_key(
            obj=obj,
            wrapper=wrapper,
            methods_to_add=methods_to_add,
            name=name,
            skip=skip,
            wrap_return_values=wrap_return_values,
            wrapped_name_func=wrapped_name_func,
            wrapping_scope_regex=wrapping_scope_regex,
        )
        _wrapped_objs[key] = wrapped
        set_original_obj()
        if obj_type in [ObjectType.FUNCTION_OR_METHOD, ObjectType.COROUTINE]:
            return wrapped
        add_methods()
        if obj_type in {ObjectType.MODULE, ObjectType.CLASS}:
            for attr_name, attr_value in members:
                if need_to_wrap():
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
                        attr_value_new = _wrap(obj=attr_value,
                                               wrapper=wrapper,
                                               methods_to_add=methods_to_add,
                                               name=get_name(attr_value, attr_name),
                                               skip=skip,
                                               wrap_return_values=wrap_return_values,
                                               wrapped_name_func=wrapped_name_func,
                                               wrapping_scope_regex=wrapping_scope_regex)
                        with suppress(Exception):
                            base_type = {
                                ObjectType.MODULE: types.ModuleType,
                                ObjectType.CLASS: type,
                            }[obj_type]
                            base_type.__setattr__(wrapped, attr_name, attr_value_new)
        else:
            wrapped_class_name = get_name(obj.__class__)
            # noinspection PyArgumentList
            wrapped_class = _wrap(obj=obj.__class__,
                                  wrapper=wrapper,
                                  methods_to_add=methods_to_add,
                                  name=wrapped_class_name,
                                  skip=skip,
                                  wrap_return_values=wrap_return_values,
                                  wrapped_name_func=wrapped_name_func,
                                  wrapped=wrapped.__class__,
                                  wrapping_scope_regex=wrapping_scope_regex)
            object.__setattr__(wrapped, '__class__', wrapped_class)
        return wrapped

    def wrap_return_values_(result):
        if wrap_return_values:
            # noinspection PyArgumentList
            result = _wrap(obj=result,
                           wrapper=wrapper,
                           methods_to_add=methods_to_add,
                           name=get_name(result, 'result'),
                           skip=skip,
                           wrap_return_values=wrap_return_values,
                           wrapped_name_func=wrapped_name_func,
                           wrapping_scope_regex=wrapping_scope_regex)
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
                    # else call original __getattribute__ and wrap the result before returning it.
                    # noinspection PyShadowingNames
                    name = args[1]
                    attr_value = obj_with_original_obj_as_self(*args, **kwargs)
                    if is_magic_name(name=name):
                        return attr_value
                    else:
                        # noinspection PyShadowingNames,PyArgumentList
                        return _wrap(obj=attr_value,
                                     wrapper=wrapper,
                                     methods_to_add=methods_to_add,
                                     name=name,
                                     skip=skip,
                                     wrap_return_values=wrap_return_values,
                                     wrapped_name_func=wrapped_name_func,
                                     wrapping_scope_regex=wrapping_scope_regex)
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

    methods_to_add = frozenset(methods_to_add)
    skip = frozenset(skip)

    if wrapped_name_func is None:
        # noinspection PyShadowingNames
        def wrapped_name_func(obj):
            _ = obj
            return '_original_obj'

    name = get_name(name, obj)
    if name is None:
        raise ValueError("name was not passed and obj.__name__ not found")

    key = make_key(
        obj=obj,
        wrapper=wrapper,
        methods_to_add=methods_to_add,
        name=name,
        skip=skip,
        wrap_return_values=wrap_return_values,
        wrapped_name_func=wrapped_name_func,
        wrapping_scope_regex=wrapping_scope_regex,
    )

    def get_module_name():
        module = inspect.getmodule(obj)
        if module:
            return module.__name__
        return ""

    def get_library_name(module_name):
        if module_name:
            return module_name.partition(".")[0]
        return ""

    def get_default_wrapping_scope_regex():
        module_name = get_module_name()
        if module_name in STDLIB_MODULE_NAMES:
            return STDLIB_MODULE_NAMES_REGEX
        else:
            library_name = get_library_name(module_name)
            return rf"{library_name}(\..*)?" if library_name else ".*"

    wrapping_scope_regex = wrapping_scope_regex or get_default_wrapping_scope_regex()

    # noinspection PyUnusedLocal
    members = []
    with suppress(ModuleNotFoundError):
        members = getmembers(object=obj)

    try:
        already_wrapped = key in _wrapped_objs
    except TypeError:
        already_wrapped = False
    module_name = get_module_name()
    if not (not module_name or re.fullmatch(wrapping_scope_regex, get_module_name())) or is_in_skip():
        wrapped = obj
    elif already_wrapped:
        wrapped = _wrapped_objs[key]
    elif members:
        wrapped = wrap_(obj=obj, name=name, members=members, wrapped=wrapped)
    else:
        wrapped = obj
        _wrapped_objs[key] = wrapped

    return wrapped


def wrap(obj, wrapper=None, methods_to_add=(), name=None, skip=(), wrap_return_values=False, clear_cache=True,
         wrapping_scope_regex=None):
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
    :param bool clear_cache: Clear wrapped objects cache after wrapping
    :param Optional[str] wrapping_scope_regex: regex for module names that should be wrapped
    :return: Wrapped `obj`
    """
    result = _wrap(
        obj=obj,
        wrapper=wrapper,
        methods_to_add=methods_to_add,
        name=name,
        skip=skip,
        wrap_return_values=wrap_return_values,
        wrapping_scope_regex=wrapping_scope_regex,
    )
    if clear_cache:
        _wrapped_objs.clear()
    return result
