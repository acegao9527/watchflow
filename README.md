# Douban Wish Quark Downloader

把豆瓣“想看/待看”列表变成一个自动化媒体入库流水线：

1. 抓取豆瓣待看条目；
2. 识别电影 / 电视剧；
3. 调用影视资源搜索服务检索夸克网盘链接；
4. 验证夸克分享链接是否有效；
5. 转存到夸克网盘的 `电影下载` / `电视剧下载`；
6. 统一命名：
   - 电影：`电影名称 (年份)/电影名称 (年份).mkv`
   - 剧集：`剧集名称 (年份)/...`（只规范顶层文件夹，不破坏集数文件名）

这个项目源自一次真实的 Agent 自动化实践：Agent 分批扫描豆瓣待看，找到可用夸克资源，保存到网盘。后续如果你的 NAS / 极空间 / 群晖会同步夸克目录，就可以形成“豆瓣待看 → 夸克 → NAS 媒体库”的自动链路。

## 特性

- 可分批续跑：`--start-index` + `--use-existing`
- 支持电影 / 电视剧分流
- 夸克链接 token API 验证，不用网页 200 假判断
- 电影主视频和字幕安全重命名
- 避免常见误命中：短剧、子串标题、剧集误入电影目录
- 不删除任何网盘文件，失败记录后继续

## 安装

```bash
git clone https://github.com/<your-name>/douban-wish-quark-downloader.git
cd douban-wish-quark-downloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp examples/config.example.json config.json
```

编辑 `config.json`，填入你自己的配置。不要提交真实配置。

## 配置

```json
{
  "douban_user_id": "你的豆瓣用户 ID",
  "quark_cookie": "你的夸克 Cookie",
  "search_endpoint": "http://127.0.0.1:8888/api/search",
  "movie_folder": "电影下载",
  "show_folder": "电视剧下载"
}
```

也可以用环境变量覆盖：

```bash
export DOUBAN_USER_ID="..."
export QUARK_COOKIE="..."
export MEDIA_SEARCH_ENDPOINT="http://127.0.0.1:8888/api/search"
```

## 快速试跑

只抓取并打印样例，不转存：

```bash
python3 src/douban_wish_quark_downloader.py \
  --config config.json \
  --max-pages 1 \
  --count 5 \
  --dry-run
```

正式保存 5 条：

```bash
python3 src/douban_wish_quark_downloader.py \
  --config config.json \
  --count 5 \
  --max-pages 5
```

复用已有缓存继续跑：

```bash
python3 src/douban_wish_quark_downloader.py \
  --config config.json \
  --use-existing \
  --start-index 100 \
  --count 20
```

只处理电影 / 电视剧：

```bash
python3 src/douban_wish_quark_downloader.py --config config.json --media-type movie --count 10
python3 src/douban_wish_quark_downloader.py --config config.json --media-type show --count 10
```

## 资源搜索接口约定

默认接口：

```text
POST /api/search
```

请求体示例：

```json
{
  "kw": "流浪地球",
  "cloud_types": ["quark"],
  "filter": {
    "exclude": ["预告", "花絮", "解说", "枪版", "TC", "TS", "CAM", "抢先"]
  }
}
```

期望返回结构兼容：

```json
{
  "data": {
    "merged_by_type": {
      "quark": [
        {"url": "https://pan.quark.cn/s/xxxx", "note": "资源标题"}
      ]
    }
  }
}
```

也兼容部分二次包裹结构：`data.data.merged_by_type.quark`。

## 安全与脱敏

- 仓库不包含豆瓣 ID、夸克 Cookie、私有搜索接口地址。
- `config.json` 已加入 `.gitignore`。
- 不输出 Cookie / token。
- 不删除网盘文件。

## 局限

- 豆瓣公开页面可能受登录状态、反爬、隐私设置影响。
- 电影 / 剧集分类是启发式规则，长剧集、短纪录片、动画条目需要人工抽查。
- 资源搜索质量取决于你的搜索接口。
- 夸克转存后有时会处于“下载中”，重命名可能需要稍后重试。

## License

MIT
