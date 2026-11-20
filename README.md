# OI 校内模拟赛 Rating

公开网站：<https://tangyixiao.github.io/oi-rating/>

排行榜应用部署在 <https://sxyz-elo-rating.pages.dev/>。本仓库保存同一份页面的副本和它发布的数据，并由定时工作流自动跟进线上改动，所以 GitHub Pages 也能打开完整的成绩榜、比赛记录、选手与数据分析。

## 数据如何保存

线上应用把整份数据存在 Cloudflare：读取对所有人开放，写入需要管理口令。页面启动时读取相对路径 `api/data`，定时同步工作流把这个接口的响应原样写进仓库：

- `api/data` —— 页面运行时读取的地址；
- `data.json` —— 同一份数据的可读副本，供测试和人直接查看。

两个文件始终是同一份字节。仓库和网站公开，其中的选手姓名与成绩也公开。

历次同步都在 Git 里留下记录。`updatedAt` 与内容都没变时，工作流不会产生提交。

## 同步工作流

`.github/workflows/sync-live-site.yml` 每八小时抓取一次线上页面与数据（05:17、13:17、21:17 UTC，即北京时间 13:17、21:17、次日 05:17），也可以手动触发：

```sh
gh workflow run sync-live-site.yml            # 抓取、开 PR 并自动合并
gh workflow run sync-live-site.yml -f merge=false   # 只开 PR，留给人看
```

`scripts/sync_live_site.py` 负责抓取。它只使用标准库，所以定时任务不安装任何依赖。脚本会先确认取回的内容仍是本应用（页面含标签页标记与数据接口路径），再校验数据的结构，任何一项不通过就放弃写入，不会用错误内容覆盖仓库。本地只用它对比差异、不写入：

```sh
python3 scripts/sync_live_site.py --check
```

工作流跑完把改动提交到 `sync/live-site` 分支，开一个 PR 并自行压缩合并；提交和合并提交都带 `Co-authored-by` 联署。它以自身令牌工作，不监听 `push` 与 `pull_request`，所以外部提交的内容碰不到写入权限。

## 本地运行

无需构建或安装应用依赖：

```sh
cd ~/oi-rating
python3 -m http.server 8080 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8080/>。请通过 HTTP 服务打开，浏览器直接打开 HTML 文件时可能无法读取数据。

## 部署

Pages 来源为 `main` 分支根目录。`.nojekyll` 让 GitHub 直接发布静态文件；页面里的路径都是相对的，所以在 `/oi-rating/` 这样的子路径下也能正常载入数据、清单与图标。

## 验证

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m playwright install chromium
python3 -m http.server 8080 --bind 127.0.0.1
# 在另一个终端执行：
.venv/bin/python tests/smoke.py --url http://127.0.0.1:8080/
```

测试用页面自带的重算逻辑逐人核对 `data.json` 里的 Rating，确认总榜、比赛、选手、数据分析四个页面显示的行数与数据一致，匿名访客看不到「导入成绩」与导出按钮，分析页的搜索与隐藏人数提示正常，比赛榜单能打开，主题选择在重载后保持，Service Worker 能注册，移动端不横向溢出，并且没有脚本错误、对外请求，`api/data` 与 `data.json` 字节相同。可以用 `--browser-executable /path/to/chromium` 指定已有浏览器。

## 项目网站

下载或克隆仓库后，用浏览器打开[中文首页](project-website/site/index.html)或 [English homepage](project-website/site/en/index.html)。两个版本都可以离线阅读。
