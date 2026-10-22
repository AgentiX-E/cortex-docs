# 迭代 #146 候选 —— 基准运行因连接被重置而死亡

## 发生了什么

在 #145 的同瞬 4+4 A/B 期间，八次基准运行之一
（`33897750172`，对照实验臂）失败了：

```
2026-09-04T17:09:38Z ##[error]terminated
TypeError: terminated
    at Fetch.onAborted (node:internal/deps/undici/undici:11473:53)
    at Fetch.terminate (node:internal/deps/undici/undici:10631:14)
    at TLSSocket.<anonymous> (node:internal/deps/undici/undici:6531:16)
```

它在一场 500 道题的运行进行到约 14 分钟时死亡，恰好在诊断步骤完成之后。
上传步骤仍然运行了，因此该运行产出了一个 **2 KB 的残桩产物**
而非干净地失败 —— 这是一个真实的隐患，因为一个天真的下载器会把那个残桩
当作一次已完成的运行来接受。

## 根因

不是产品 bug。两件独立的事：

1. **峰值并发。** 该 A/B 在 18 秒之内调度了全部 8 次运行，因此八个 500 道题的
   基准同时击中 LLM 提供方。现有的重试层
   （`packages/cortex-llm/src/retry.ts`，5 次重试、
   指数退避合计约 31 秒，且它*确实*会重试网络错误）
   不够：限流持续的时间超过了整个重试窗口。

2. **没有按请求的超时。** `retryableFetch` 不传任何 `AbortSignal`，
   因此一个挂起而非重置的连接会无限期挂起。唯一的兜底
   是工作流的 240 分钟超时。因此挂起不会被
   转换为一个可重试的错误。

## 为何此前未被捕获

先前的 A/B 使用了同样的 8 个一次性调度，并运气不错。失效率
直到现在才可见，且流水线中没有任何东西验证产物，所以
一个残桩与一次真实运行本会是不可区分的。

## 修复，按优先级排序

- **P0（工装，已在 #145 完成）：** `download_ab_tr_two_event.sh` 现在验证
  每一个产物 —— 它必须同时包含逐题诊断文件*和*一份
  `questionCount` 为 500 的报告 —— 并拒绝其他任何东西。
- **P1（工装）：** 把 8 次运行作为四个同瞬**配对**来调度，彼此相隔
  几分钟，而非一次性全部发出。弃权的漂移是在
  小时尺度上运作的，因此约 20 分钟的散布可忽略不计，而峰值并发从 8
  降到 2。
- **P2（产品）：** 给 `retryableFetch` 一个 `AbortSignal.timeout()`，使一个挂起的
  请求变成一个可重试的错误，而非一次无界等待。需要它自己的
  TDD 迭代，测试覆盖 超时 → 重试 → 成功，且不得
  混进一个其归因依赖于 LLM 调用模式保持
  固定的 A/B 中。

## 有意现在不做

P2 改变每一次 LLM 调用的网络行为，这会污染
#145 的归因。它等它自己的迭代。

---

# 2026-09-11 —— 一次 push 期间的 `github.com` TLS 中断

## 发生了什么

推送 `624e241` 反复失败，出现两个交替的错误：

```
fatal: unable to access 'https://github.com/AgentiX-E/cortex.git/':
  gnutls_handshake() failed: The TLS connection was non-properly terminated.
fatal: unable to access 'https://github.com/AgentiX-E/cortex.git/':
  GnuTLS recv error (-110): The TLS connection was non-properly terminated.
```

这是反复出现的 github TLS 不稳定性，而通常的补救 —— 从 `~/.user_hosts`
重新固定 `/etc/hosts` 然后重试 —— 这次**没有奏效**。三次
重试，加上 `http.version=HTTP/1.1`，全部失败。

## 诊断

通过分别探测端点与 IP 缩小了该失败：

| 探测 | 结果 |
|---|---|
| `curl https://github.com` | `SSL_ERROR_SYSCALL`，代码 000 |
| `curl https://api.github.com` | **200** |
| `curl https://codeload.github.com` | **301** |
| `curl https://objects.githubusercontent.com` | **404** |
| TCP 连接到 140.82.121.4 / .113.4 / .112.4 / .114.4 / 20.205.243.166 : 443 | 全部 **OK** |

因此：到每一个端点的 TCP 都是好的，`api.github.com` 正常提供 TLS，
只有 **`github.com` 这个 git 主机**拒绝完成握手。这
把一个主机特定的 TLS 中断与本地路由或证书
问题区分开，并意味着 `/etc/hosts` 固定这个变通办法帮不上忙 —— 那个固定
本就已经正确。

## 解决

自行清除。约 10 分钟后重新探测三个候选 IP，三个都返回
**200**，随后 push 在第一次尝试时成功。

## 教训

当一次 push 以 GnuTLS 错误失败时，不要假定再一次 hosts 重固定就能
修好它。在 `github.com` 之外一并探测 `api.github.com` 和一个原始 TCP 连接：若
TCP 是通的、`api.` 在提供服务而 `github.com` 不是，那就是一次主机侧
中断，唯一正确的行动是等待并重试，而非改动配置。
在那样的状态下反复折腾 `/etc/hosts`，有留下一个错误固定
给下一次 push 的风险。
