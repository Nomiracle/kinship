# 测试素材约定

- **只允许合成数据。** 真实人物、真实照片、真实日期一律不得出现在本目录 —— 仓库是公开的。
- 图片用 `make_fixture.py` 现场生成（纯标准库，不依赖 Pillow）：

  ```bash
  python3 tests/fixtures/make_fixture.py
  ```

- 示例档案固定用假人：`示例用户`（self）、`小美`（partner）、`阿明`（friend），
  生日统一 `1990-01-01`，忌口统一「香菜」。要新维度就照着加，别抄真实数据。
- `generated/` 下的产物是构建物，已 gitignore（见根目录 `.gitignore` 的例外规则）。
