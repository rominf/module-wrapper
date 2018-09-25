Welcome to module-wrapper's documentation!
==========================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Installation
============

To install from `PyPI  <https://pypi.org/project/module-wrapper/>`_ run::

    $ pip install module-wrapper

Usage
=====

Example from `aioify <https://github.com/yifeikong/aioify>`_::

    from functools import wraps, partial
    import asyncio

    import module_wrapper


    __all__ = ['aioify']


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
            return 'create', wrap(cls)

        return module_wrapper.wrap(obj=obj, wrapper=wrap, methods_to_add={create}, name=name)

API
===

.. automodule:: module_wrapper
    :members:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
