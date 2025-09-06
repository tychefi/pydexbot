



tcli get currency balance flon.mtoken botuser11111 USDT
tcli get currency balance flon.mtoken botuser11112 USDT
tcli get currency balance flon.mtoken botuser11113 USDT

users=(botuser11111 botuser11112 botuser11113)
for user in "${users[@]}"; do
    echo "---------- $user ---------"
    tcli get currency balance flon.token "$user" FLON
    tcli get currency balance flon.mtoken "$user" USDT
done

tcli get table tokenxmm1111 tokenxmm1111 global

tcli transfer flonian tokenxmm1111 "100.0000 USDT" --contract flon.mtoken -p flonian



tcli get table buylowsellhi buylowsellhi trademarkets -L flon.usdt -U flon.usdt -l 1
