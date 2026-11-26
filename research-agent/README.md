# research-agent

**给定主题或一组来源，自动抽要点、生成带出处的报告。**

标准库 Python（urllib + html.parser + re），无 API key，无第三方依赖。

```bash
# 给定来源（推荐，结果可控）
python research.py --query "asyncio 协程 事件循环" \
  --urls https://www.runoob.com/python3/python-asyncio.html \
         https://liaoxuefeng.com/books/python/async-io/asyncio/ \
  --out report.md

# 自动搜索（Bing HTML；可能被反爬降级，见下）
python research.py --query "python asyncio" --top 4
```

## 四个步骤

```
search → fetch → extract → compose
  │        │        │         └─ 每条要点都带来源链接
  │        │        └─ 句子级打分（DF 加权 + 位置先验），噪声过滤
  │        └─ 去 HTML，跳过 script/style/nav/footer
  └─ Bing HTML 结果页解析
```

每一步都打印进度和耗时，失败单独报告，不静默跳过。

## 三个刻意的设计

**1. 每条结论从抽取那一刻就绑着来源。**
`sentence` 和 `url` 一起进列表，报告是直接拼出来的，所以不可能出现「没有出处的结论」。一个追不回原文的摘要比没有摘要更糟。

**2. 抓取失败要被看见。**
5 个来源挂了 2 个，报告会专门列一节「Not fetched」并写明「这是部分报告」。静默的部分结果读起来像完整结果——这是最危险的一类错误。

**3. 中文用 bigram，不用分词器。**
不引入 jieba 这类依赖，中文按二元组切：「事件循环」切成「事件/件循/循环」，所以只说「循环」的句子也能命中说「事件循环」的查询。代价是精度略低，好处是零依赖且语言无关。

## 噪音过滤

剥完 HTML 还剩大量样板文字（「欢迎来到…」「请启用 JavaScript」「版权所有」）。提取前会过滤：

- 命中样板词表（welcome to / cookie / 登录 / 隐私政策 / 本页显示…）
- 句子开头就是页面标题（说明是标题重复，不是内容）

## 已知限制

| 限制 | 原因 | 生产上怎么办 |
|---|---|---|
| **`--query` 可能搜到泛化结果** | Bing 对自动化请求会降级（实测：查「python asyncio」返回 python.org 首页） | 接 SearXNG / Serper / Brave Search API；或直接用 `--urls` 模式 |
| 单页只取 2 句 | 避免报告变成文章摘抄 | 按需调 `per_page` |
| 不做跨来源综合 | 没有模型参与，纯抽取 | 接 LLM 做归纳；但要保留逐句溯源，否则会丢可核查性 |
| 只处理静态 HTML | 不执行 JS | SPA 用渲染服务（Playwright）先出 HTML |

## 实测

一次真实运行（2026-11-25，两个中文技术站）：

```
[2/4] fetch   2 page(s)
      ok   13352 chars  https://www.runoob.com/python3/python-asyncio.html
      ok    4899 chars  https://liaoxuefeng.com/books/python/async-io/asyncio/
[3/4] extract query terms over 2 page(s)
      4 sentence(s) kept
[4/4] compose
      wrote report.md (1892 bytes)
```

0.3 秒完成，4 条要点全部指向具体来源。

## License

MIT
