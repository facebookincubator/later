=====
later
=====
.. image:: https://github.com/facebookincubator/later/workflows/later_ci/badge.svg
    :target: https://github.com/facebookincubator/laster/actions

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black


**What is** ``later``?

later is a play on Async not happening now but at some point in the future.
It was also an awesome name for a toolkit for writing AsyncIO applications. The
*batteries* if you will for AsyncIO.

later offers the following functions:

    - **asyncio** `Event` enhancements
        - ``BiDirectionalEvent`` - Back channel of information for the setter to ensure the waiter has called wait() a second time
    - **asyncio** `Task` enhancements
        - `Watcher` - Watch tasks and ensure they don't die - take action when they do
    - **asyncio** Unittesting enhancements
        - `TestCase` - Use in place of `IsolatedAsyncioTestCase` for more wins
        - `IsolatedAsyncioTestCase` is backported for 3.7 users


`later` currently backports 3.8's `async_case` + `mock` libraries for 3.7 users.

License
==========
`later` is Apache licensed, as found in the LICENSE `file <https://github.com/facebookincubator/later/blob/master/LICENSE>`_
