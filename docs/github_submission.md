# GitHub提交说明

建议将整个`stage05_equity_change_timeline_engineering`目录提交到仓库的阶段成果目录，而不是只上传Excel。

## 推荐命令

```bash
git status
git add stage05_equity_change_timeline_engineering
git commit -m "feat(stage05): add approved timeline data and validation pipeline"
git push
```

## 提交内容应包含

- 最终验收Excel；
- JSON和CSV派生数据；
- JSON Schema；
- Excel导出脚本；
- 数据校验脚本；
- 单元测试；
- 自动校验报告；
- README、数据字典和文件校验和。

## 不建议提交

- `pending_user_review`版本；
- 临时预览图片；
- Python缓存目录；
- 重复复制的源PDF。

源PDF应统一保存在仓库既有的原始资料目录，并在README中说明其为唯一主要事实来源。
