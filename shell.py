# Copyright (c) 2023 0dminnimda <0dminnimda.contact@gmail.com>.
# All rights reserved.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of the full source code tree.
# Full source code available at: <https://github.com/0dminnimda/ebash>

# The above notice shall be included in all
# copies or substantial portions of the Software.

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from subprocess import Popen
from typing import IO, Dict, Iterable, Iterator, TypeVar


class Stream(Enum):
    PIPE = subprocess.PIPE
    STDOUT = subprocess.STDOUT
    STDERR = min(subprocess.PIPE, subprocess.STDOUT, subprocess.DEVNULL) - 1
    DEVNULL = subprocess.DEVNULL


T1 = TypeVar("T1")
T2 = TypeVar("T2")


Process = Popen[bytes]


Args = Iterable[T1]
Kwargs = Dict[str, T2]


# XXX: use dict so it's easier to set kwargs
@dataclass
class Params:
    args: Args
    stdin: Stream | None
    stdout: Stream
    stderr: Stream
    kwargs: Kwargs


@dataclass
class Executor(ExitStack):
    return_code: int = field(default=0, init=False)
    encoding: str = field(init=False)
    _stdin: IO[bytes] | None = field(default=None, init=False, repr=False)
    _stdout: IO[bytes] | None = field(default=None, init=False, repr=False)
    _stderr: IO[bytes] | None = field(default=None, init=False, repr=False)
    _processes: list[Process] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__init__()

    def reset(self) -> None:
        if len(self._processes) != 0:
            self.close()
        self.return_code = 0
        self._stdin = None
        self._stdout = None
        self._stderr = None
        self._processes = []

    def prepare_params(self, params: Params) -> tuple[Args, Kwargs]:
        stdin: object = None if params.stdin is None else params.stdin
        stdout: object = None if params.stdout == Stream.STDOUT else params.stdout
        stderr: object = None if params.stderr == Stream.STDERR else params.stderr

        stdin = stdin.value if isinstance(stdin, Stream) else stdin
        stdout = stdout.value if isinstance(stdout, Stream) else stdout
        stderr = stderr.value if isinstance(stderr, Stream) else stderr

        if "stdin" not in params.kwargs:
            params.kwargs.update(stdin=stdin)
        params.kwargs.update(stdout=stdout)
        params.kwargs.update(stderr=stderr)
        return params.args, params.kwargs

    def make_popen(self, params: Params) -> Process:
        args, kwargs = self.prepare_params(params)
        return self.enter_context(Process(*args, **kwargs))

    def execute(
        self,
        params_list: list[Params],
        input: str | None = None,
        close_stdin: bool = True,
        encoding: str = "utf-8",
    ) -> Executor:
        if len(params_list) == 0:
            raise ValueError(
                "No parameters were found, you should supply at least one parameter"
            )
        self.reset()

        self.encoding = encoding

        params = params_list[0]
        if input is not None and params.stdin != Stream.PIPE:
            raise ValueError("To have an input the first stdin should be Stream.PIPE")
        self._processes.append(self.make_popen(params))

        for params in params_list[1:]:
            if params.stdin == Stream.STDOUT:
                params.kwargs["stdin"] = self._processes[-1].stdout
            elif params.stdin == Stream.STDERR:
                params.kwargs["stdin"] = self._processes[-1].stderr
            elif params.stdin == Stream.DEVNULL:
                params.kwargs["stdin"] = params.stdin.value
            else:
                raise ValueError(
                    f"Invalid stdin for piped operation[{params.args}]: {params.stdin}"
                )
            self._processes.append(self.make_popen(params))

        self._stdin = self._processes[0].stdin
        self._stdout = self._processes[-1].stdout
        self._stderr = self._processes[-1].stderr

        self.write(input)
        if close_stdin and self._stdin:
            self._stdin.close()
        return self

    __call__ = execute

    def write(self, input: str | None) -> None:
        if not input:
            return

        if not self._stdin:
            raise ValueError("stdin is not set")

        os.write(self._stdin.fileno(), input.encode(self.encoding))

    def read_stdout(self, n: int = 2**32) -> str:
        if not self._stdout:
            raise ValueError("stdout is not set")

        return os.read(self._stdout.fileno(), n).decode(self.encoding)

    def read_stderr(self, n: int = 2**32) -> str:
        if not self._stderr:
            raise ValueError("stderr is not set")

        return os.read(self._stderr.fileno(), n).decode(self.encoding)

    def get_output(self) -> tuple[str | None, str | None]:
        out = self._stdout.read().decode(self.encoding) if self._stdout else None
        err = self._stderr.read().decode(self.encoding) if self._stderr else None

        # XXX: should this condition be here?
        # should executor also try to imitate shell and not just wrap subprocess?
        if out and out.endswith("\n"):
            out = out[:-1]

        return out, err

    def __enter__(self):
        return super().__enter__()

    def __exit__(self, *exc_details):
        try:
            if self._stdin:
                self._stdin.close()
            if self._stdout:
                self._stdout.close()
            elif self._stderr:
                self._stderr.close()
            self._processes[-1].wait()
        except:  # noqa # Including KeyboardInterrupt, communicate handled that.
            for process in self._processes:
                process.kill()
                # We don't call process.wait() as super().__exit__ does that for us.
            raise

        self.return_code = self._processes[-1].poll() or 0

        self._processes.clear()
        return super().__exit__(*exc_details)

    def close(self) -> None:
        super().close()


RUN = object()


@dataclass(repr=False)
class Shell:
    """
    This class works like usual bash/shell and can be used
    as a replacement for them when there's a need to use the power of Python

    Author: 0dminnimda
    """

    _return_code: int = field(default=0, init=False)
    _stdout: str | None = field(default=None, init=False)
    _stderr: str | None = field(default=None, init=False)
    _executor: Executor = field(default_factory=Executor, init=False, repr=False)
    _input: str | None = field(default=None, init=False, repr=False)
    _args: list[Params] = field(default_factory=list, init=False, repr=False)

    def __repr__(self) -> str:
        names = ["return_code", "stdout", "stderr"]
        items = [f"{name}={getattr(self, name)!r}" for name in names]
        return f"{type(self).__name__}({', '.join(items)})"

    @property
    def return_code(self):
        self.pipe(fail=False).run()
        return self._return_code

    @property
    def stdout(self):
        self.pipe(fail=False).run()
        return self._stdout

    @property
    def stderr(self):
        self.pipe(fail=False).run()
        return self._stderr

    @property
    def output(self) -> str:
        return self.stdout or self.stderr or ""

    def __bool__(self) -> bool:
        return self.return_code == 0

    @property
    def failed(self) -> bool:
        return not self

    @property
    def succeeded(self) -> bool:
        return bool(self)

    @staticmethod
    def argv(index: int, default: str = "") -> str:
        if index >= len(sys.argv):
            return default
        return sys.argv[index]

    def _execute(self, close_stdin: bool = True) -> Executor:
        if self._input:
            self._args[0].stdin = Stream.PIPE
        self._executor.execute(self._args, self._input, close_stdin, encoding="utf-8")
        self._input = None
        return self._executor

    def run(self) -> Shell:
        if self._args:
            with self._execute():
                self._stdout, self._stderr = self._executor.get_output()
            self._return_code = self._executor.return_code
            self._args.clear()
        return self

    @contextmanager
    def inject(self, close_stdin: bool = True):  # -> Iterator[tuple[]]:
        if not self._args:
            raise RuntimeError(
                "No commands found, pipe some commands and don't use run()"
            )
        with self._execute(close_stdin):
            self._args.clear()
            yield (
                self._executor.write,
                self._executor.read_stdout,
                self._executor.read_stderr,
            )
            self._stdout, self._stderr = self._executor.get_output()
        self._return_code = self._executor.return_code

    def __call__(
        self,
        command: str,
        stdout: Stream = Stream.STDOUT,
        stderr: Stream = Stream.STDERR,
        stdin: Stream | None = None,
    ) -> Shell:
        """Adds command into the piped commands list.

        `stdout` and `stderr` control where the process will write the data.

        `stdin` controls where the process will read the data from.
        `stdin` will be initialized (`default=None`) to `Stream.STDOUT`
        if the command list is not empty.
        """

        # subprocess does not support changing writing target for other created stream
        # and you don't really need it when you have that option for stderr
        if stdout == Stream.STDERR:
            raise ValueError("It's not possible to direct stdout into stderr")

        if stdin is None and self._args:
            stdin = Stream.STDOUT
        elif stdin == Stream.PIPE and self._args:
            raise ValueError(
                "It's not possible to direct pipe into stdin for piped commands"
            )
        elif stdin in (Stream.STDOUT, Stream.STDERR) and not self._args:
            raise ValueError(
                "It's not possible to direct stdout or stderr into stdin"
                " for the first piping command,"
                " actual stdout and stderr are not readable"
            )

        self._args.append(
            Params(
                args=tuple([shlex.split(command)]),
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                kwargs=dict(),
            )
        )

        return self

    def pipe(self, fail: bool = True) -> Shell:
        if len(self._args) != 0:
            self._args[-1].stdout = Stream.PIPE
        elif fail:
            raise RuntimeError(
                "No commands were found, try to add a command before piping"
            )
        return self

    def __or__(self, other) -> Shell:
        if other is RUN:
            return self.run()
        if isinstance(other, str):
            self.pipe(fail=False)
            return self.__call__(other)
        if isinstance(other, type(self)):
            return self

        return NotImplemented

    def input(self, data: str, can_override: bool = False) -> Shell:
        if not can_override and self._args:
            raise RuntimeError(
                "It's not possible to input the data in the middle of the pipe"
            )
        self._input = data
        return self

    def __rrshift__(self, other) -> Shell:
        if isinstance(other, str):
            return self.input(other, can_override=True)
        return NotImplemented
