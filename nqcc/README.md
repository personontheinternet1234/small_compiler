
```bash
chmod +x nqcc_stage1.py
./nqcc_stage1.py examples/return_2.c
./examples/return_2
echo $?
```

```bash
./nqcc_stage1.py --target 32 examples/return_2.c
```

```bash
./nqcc_stage1.py --emit-assembly --keep-assembly examples/return_2.c
cat examples/return_2.s
```

```bash
./nqcc_stage1.py --print-ast --emit-assembly examples/return_2.c
```

```bash
./test_stage1.py
```
