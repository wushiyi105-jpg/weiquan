# examples

四份脱敏后的真实纠纷描述,覆盖无理由退货、货不对板、虚假宣传与定制例外。

| 文件 | 场景 | 关注点 |
|---|---|---|
| `case-01.txt` | 蓝牙耳机一侧没声音 | 七天无理由倒计时与三包窗口 |
| `case-02.txt` | 羽绒服颜色不符 | 无理由已过期,改走质量路径 |
| `case-03.txt` | 笔记本翻新机 | 「假一赔十」承诺与虚假宣传 |
| `case-04.txt` | 定制窗帘尺寸错 | 定制例外与赠品扣减 |

`out/` 里是每份输入的完整输出,由离线模式生成,不调用模型:

```bash
pip install -e .
python -m weiquan --mock check --file examples/case-01.txt --sign 2026-11-21 > examples/out/case-01.md
```

输出里的「距今 N 天」「剩 N 天」以运行当天为基准,同一天跑可逐字复现。
