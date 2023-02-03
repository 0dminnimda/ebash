import sys

from shell import RUN, Shell, Stream

sh = Shell()
print(sh)
exe = repr(sys.executable)

# echo "Hello world!"
sh('echo "Hello world!"').run()  # we will use RUN instead for the rest
sh('echo "Hello world!"') | RUN

# echo "SoMe WeIrd DaTa" | sha256sum
sh('echo "SoMe WeIrd DaTa"') | "sha256sum" | RUN

# sha256sum <<< "SoMe WeIrd DaTa"
sh.input("SoMe WeIrd DaTa")("sha256sum") | RUN
sh.input("SoMe WeIrd DaTa") | "sha256sum" | RUN
"SoMe WeIrd DaTa" >> sh("sha256sum") | RUN

# DATA_HASH=$(echo "SoMe WeIrd DaTa" | sha256sum)
# or DATA_HASH=$(sha256sum <<< "SoMe WeIrd DaTa")
data_hash = ("SoMe WeIrd DaTa" >> sh | "sha256sum").output

# echo "Hash - $DATA_HASH"
print(f"Hash - {data_hash}")

# false || echo "It failed"
sh("false").run() or print("It failed")
sh("false") | RUN or print("It failed")

# true && echo "So true!"
sh("true").run() and print("So true!")
sh("true") | RUN and print("So true!")

# false; echo $?
print(sh("false").return_code)  # will also run automatically for output, bool(sh), ...

# if [[ $1 ]]; then
#     exit 2
# else
#     echo "Running!"
#     $0 argument
#     echo "Result - $?"
# fi
if sh.argv(1):
    exit(2)
else:
    print("Running!")
    sh(f"'{exe}' {sh.argv(0)} argument") | RUN
    print(f"Result - {sh.return_code}")

# do_something_that_takes_a_lot_of_time & do_other_thing
# parallel execution is currently not implemented

# (cd somewhere/else)
# spawning subshells is also not implemented

generator = """
import time
for i in range(5):
    print(f'Hi-{i}, sent {time.time()}')
    time.sleep(0.5)
"""

echoer = """
import sys
import time
for _ in range(5):
    print(f'Echoer-{sys.argv[1]} got {input()!r} at {time.time()}')
"""

# no buffering while piping fow arbitrary number of pipes
# python3 -u -c "$GENERATOR" | python3 -c "$ECHOER" 1
sh(f'{exe} -u -c "{generator}"') | f'{exe} -c "{echoer}" 1' | RUN

# python3 -u -c "$GENERATOR" | python3 -c "$ECHOER" 1 | python3 -c "$ECHOER" 2
sh(f'{exe} -u -c "{generator}"') | f'{exe} -c "{echoer}" 1' | f'{exe} -c "{echoer}" 2' | RUN  # fmt: skip

# read from the stdout character by character
# (I don't want to think about how to implement it in bash)
sh(f'{exe} -u -c "{generator}"')
with sh.inject() as process:
    while r := process.stdout.read(1):
        print(end=" " + r)
    print("End!\n")

std_out_n_err = """
import sys
print('Err', file=sys.stderr)
print('Out')
"""

# python3 -c "$STD_OUT_N_ERR" 2>&1
sh(f'{exe} -c "{std_out_n_err}"', stderr=Stream.STDOUT).run()

# python3 -c "$STD_OUT_N_ERR" 2>&1
sh(f'{exe} -c "{std_out_n_err}"', stderr=Stream.DEVNULL).run()
