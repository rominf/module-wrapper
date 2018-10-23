from typing import Any, Callable, Collection, Tuple


def wrap(obj: Any,
         wrapper: Callable[[Callable], Callable] = None,
         methods_to_add: Collection[Callable[[Callable], Tuple[str, Callable]]] = (),
         name: str = None,
	 skip: Collection[str] = ()) -> Any:
    ...
