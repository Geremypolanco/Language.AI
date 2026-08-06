"""One module per job_type's actual generation logic. audio.py is the only
real one today; a future image.py/embedding.py/etc. follows the same
shape (an `execute(payload) -> result` coroutine + a `validate(result) ->
list[str]` function) and gets wired up in ../bootstrap.py."""
