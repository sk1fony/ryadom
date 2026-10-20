#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
sh ./start.sh "$@"
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nНажмите Enter, чтобы закрыть окно'
    read -r unused
fi
exit "$result"
