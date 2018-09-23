# module-wrapper - module wrapper Python library
## Installation
To install from PyPI: https://pypi.org/project/module-wrapper/ run:
```shell
$ pip install module-wrapper
```

## Usage
Example from https://github.com/rominf/aioify:
```pyhton
from functools import wraps, partial
import asyncio

import module_wrapper


def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)
    return run


def aioify(obj, name=None):
    def create(cls):
        return wrap(cls)

    return module_wrapper.wrap(obj=obj, wrapper=wrap, methods_to_add={create}, name=name)
```
