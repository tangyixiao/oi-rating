# OI 校内模拟赛 Rating

公开网站：<https://tangyixiao.github.io/oi-rating/>

从指定内网应用归档并适配到 GitHub Pages，保留成绩导入、比赛管理、总榜、选手、数据分析、JSON 导出/导入和原有 Rating 算法。初始数据为 `oi-rating-backup-2026-10-14.json`：53 位选手、108 场比赛。

## 数据如何保存

页面首次打开会读取仓库中的 `data.json`。页面中的修改只保存在当前浏览器，不会修改其他人的榜单；重载页面会保留本机修改。设置页可以导出 JSON，或在确认后重新载入公开数据。

要更新所有人看到的数据，在页面中完成修改，导出 JSON，用它替换仓库的 `data.json`，提交并推送。GitHub Pages 会重新发布。这里不提供云端共享写入或管理口令后端。

仓库和网站公开，`data.json` 中的选手姓名与成绩也公开。

## 本地运行

无需构建或安装应用依赖：

```sh
cd ~/oi-rating
python3 -m http.server 8080 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8080/>。请通过 HTTP 服务打开，浏览器直接打开 HTML 文件时可能无法读取 JSON。

## 部署

Pages 来源为 `main` 分支根目录。`.nojekyll` 让 GitHub 直接发布静态文件；数据使用相对 URL，可在仓库路径下正常载入。

## 验证

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m playwright install chromium
python3 -m http.server 8080 --bind 127.0.0.1
# 在另一个终端执行：
.venv/bin/python tests/smoke.py --url http://127.0.0.1:8080/
```

测试检查备份中的 Rating、53 位选手及 108 场比赛、六个标签页、分析筛选、本机修改后重载、取消/确认恢复、慢网络下本机和其他标签页修改的保护、JSON 导出/导入、移动布局，以及没有脚本错误、网络写入和内网请求。可以用 `--browser-executable /path/to/chromium` 指定已有浏览器。

## 本机原始归档

本机 `archive/` 保存原始 HTML、数据接口响应、提供的 JSON、来源和 SHA-256 清单。原始归档、测试截图和 Python 虚拟环境不提交到公开仓库。抓取只读取站点入口及其直接引用的数据接口；没有源服务器代码。

## 项目网站

下载或克隆仓库后，用浏览器打开[中文首页](project-website/site/index.html)或 [English homepage](project-website/site/en/index.html)。两个版本都可以离线阅读。
