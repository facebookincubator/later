=====
later
=====
.. image:: https://github.com/facebookincubator/later/actions/workflows/ci.yml/badge.svg?branch=main
    :target: https://github.com/facebookincubator/later/actions


.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black


**What is** ``later``?

later is a play on Async not happening now but at some point in the future.
It was also an awesome name for a toolkit for writing AsyncIO applications. The
*batteries* if you will for AsyncIO.

later is a collection of asyncio *batteries* created at Meta for supporting asyncio
services. 

later offers the following:
    - **Unittesting** 
        - `later.unittest.TestCase` - An `IsolatedAsyncioTestCase` that insures tasks are not left orphaned and asyncio never calls its error handler. 
        - `later.unittest.mock.AsyncContextManager` - A factory for easy mocking out `AsyncContextManager` 
    - **Tasks***
        - `later.cancel` - The *correct* way to cancel a Task/Future and insure it is awaited
        - `later.as_task` - Decorator to turn coroutines into Tasks. 
        - `later.Watcher` - Watch tasks and ensure they don't die - take action when they do. This is kinda like a `asyncio.TaskGroup`
        - `later.herd` - A Decorator that provides coroutines with basic thundering herd protection. 
        - `later.task.TaskSentinel` - A Completed Future, a default value for a `asyncio.Task` argument so you don't also have to accept None. 
    - **Synchronization**
        - `later.event.BiDirectionalEvent` - two way `asyncio.Event` for Handshake style synchronization. 

License
==========
`later` is Apache licensed, as found in the LICENSE `file <https://github.com/facebookincubator/later/blob/master/LICENSE>`_
