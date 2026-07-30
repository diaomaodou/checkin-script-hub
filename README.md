# QL Script Hub

> 🚀 个人青龙面板脚本库 - 签到、监控一站式解决方案

中文 | [English](README_EN.md)

[![GitHub stars](https://img.shields.io/github/stars/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/network)
[![GitHub issues](https://img.shields.io/github/issues/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/issues)
[![License](https://img.shields.io/github/license/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/blob/main/LICENSE)

## 📋 项目简介

QL Script Hub 是一个专为青龙面板打造的综合性脚本库，提供签到、监控等多种类型的自动化脚本。所有脚本均经过测试，确保稳定可靠。

## ✨ 功能特性

- 🎯 **多样化脚本** - 涵盖签到、监控等多种场景
- 🔧 **易于配置** - 统一的配置文件格式，简单易懂
- 📦 **模块化设计** - 清晰的目录结构，便于管理和扩展
- 🛡️ **安全可靠** - 所有脚本均经过测试，保证安全性
- 📝 **详细文档** - 每个脚本都有详细的使用说明
- 🔄 **持续更新** - 定期更新维护，修复问题和添加新功能

## 📁 目录结构

```
ql-script-hub/
├── README.md              # 项目说明文档
├── LICENSE                # 开源许可证
├── aliyunpan_checkin.py   # 阿里云盘签到脚本
├── baiduwangpan_checkin.py # 百度网盘签到
├── quark_signin.py        # 夸克网盘签到脚本
├── ty_netdisk_checkin.py  # 天翼云盘签到
├── passnat_checkin.py     # PassNAT签到脚本
├── tsthb_checkin.py       # 塔斯汀汉堡签到脚本
└── archive/               # 已归档脚本（不再维护）
    └── leaflow_checkin.py # leaflow签到脚本
```

## 🚀 快速开始

### 环境要求

- 青龙面板 2.10+
- Node.js 14+

### 安装步骤

1. **拉取仓库**
   ```bash
   # 在青龙面板订阅管理中添加订阅
   # 订阅地址：https://github.com/agluo/ql-script-hub.git
   ```

<img width="774" height="1112" alt="image" src="https://github.com/user-attachments/assets/de6cf07f-7af2-42b9-8321-c2ccc542820b" />

2. **配置环境变量**

| 变量名              | 说明                | 是否必需 | 示例值                                             | 备注                              |
| ------------------- | ------------------- | -------- | -------------------------------------------------- | --------------------------------- |
| `TG_BOT_TOKEN`    | Telegram机器人Token | 推荐     | `1234567890:AAG9rt-6RDaaX0HBLZQq0laNOh898iFYaRQ` | 获取方式见下方说明                |
| `TG_USER_ID`      | Telegram用户ID      | 推荐     | `1434078534`                                     | 获取方式见下方说明                |
| `PUSH_KEY`        | Server酱推送Key     | 可选     | `SCTxxxxxxxxxxxxxxxxxxxxx`                       | 微信推送，访问 sct.ftqq.com 获取  |
| `PUSH_PLUS_TOKEN` | Push+推送Token      | 可选     | `xxxxxxxxxxxxxxxxxx`                             | 微信推送，访问 pushplus.plus 获取 |
| `DD_BOT_TOKEN`    | 钉钉机器人Token     | 可选     | `xxxxxxxxxxxxxxxxxx`                             | 钉钉群机器人                      |
| `DD_BOT_SECRET`   | 钉钉机器人密钥      | 可选     | `xxxxxxxxxxxxxxxxxx`                             | 钉钉群机器人密钥（可选）          |
| `BARK_PUSH`       | Bark推送地址        | 可选     | `https://api.day.app/your_key/`                  | iOS Bark推送                      |

#### ☁️ 夸克网盘签到配置

| 变量名           | 说明           | 是否必需       | 示例值               | 备注                      |
| ---------------- | -------------- | -------------- | -------------------- | ------------------------- |
| `QUARK_COOKIE` | 夸克网盘Cookie | **必需** | `cookie1&&cookie2` | 多账号用 `&&`或回车分隔 |

#### ☁️ 阿里云盘签到配置

| 变量名                   | 说明                  | 是否必需       | 示例值                      | 备注                            |
| ------------------------ | --------------------- | -------------- | --------------------------- | ------------------------------- |
| `ALIYUN_REFRESH_TOKEN` | 阿里云盘refresh_token | **必需** | `crsh166bdfde4751a4c0...` | 多账号用换行分隔 |
| `AUTO_UPDATE_TOKEN`    | 自动更新Token         | 可选           | `true`                    | 默认 `true`，自动维护token    |
| `PRIVACY_MODE`         | 隐私保护模式          | 可选           | `true`                    | 默认 `true`，脱敏显示敏感信息 |

#### 🍔 塔斯汀汉堡签到配置

| 变量名           | 说明             | 是否必需       | 示例值                      | 备注                       |
| ---------------- | ---------------- | -------------- | --------------------------- | -------------------------- |
| `tsthbck` | 塔斯汀汉堡user-token | **必需** | `xxxxx` | 微信小程序抓包获取，多账号用换行分隔 |

#### ☁️ 百度网盘配置

| 变量名           | 说明       | 示例                         |
| ---------------- | ---------- | ---------------------------- |
| `BAIDU_COOKIE` | 网站Cookie | `BDUSS=xxx; STOKEN=xxx...` |
| `PRIVACY_MODE` | 隐私模式   | `true`                     |

#### ☁️ 天翼云盘配置

| 变量名          | 说明       | 示例                        | 备注       |
| --------------- | ---------- | --------------------------- | ---------- |
| `TY_USERNAME` | 登录手机号 | `13812345678\n13987654321` | 多账号换行 |
| `TY_PASSWORD` | 登录密码   | `password1\npassword2`     |            |

#### 🌐 PassNAT签到配置

| 变量名           | 说明             | 是否必需       | 示例值                      | 备注                       |
| ---------------- | ---------------- | -------------- | --------------------------- | -------------------------- |
| `PASSNAT_SK` | PassNAT接口密钥 | **必需** | `sk_xxxxx` | 多账号用换行分隔 |

#### ⏰ 随机化配置（所有脚本共用）

| 变量名               | 说明               | 是否必需 | 示例值   | 备注                            |
| -------------------- | ------------------ | -------- | -------- | ------------------------------- |
| `RANDOM_SIGNIN`    | 启用随机签到       | 可选     | `true` | `true`启用，`false`禁用     |
| `MAX_RANDOM_DELAY` | 随机延迟窗口（秒） | 可选     | `3600` | `3600`=1小时，`1800`=30分钟 |

---

## 🔧 获取方式说明

### 📱 Telegram配置获取

1. **创建机器人**: 与 [@BotFather](https://t.me/botfather) 对话，发送 `/newbot` 创建机器人
2. **获取Token**: 创建完成后会收到 `TG_BOT_TOKEN`
3. **获取用户ID**: 与 [@userinfobot](https://t.me/userinfobot) 对话获取 `TG_USER_ID`

### 🍪 Cookie获取方式

#### 夸克网盘 Cookie

1. 浏览器访问 [夸克网盘](https://pan.quark.cn/) 并登录
2. F12 开发者工具 → Network → 刷新页面
3. 找到请求头中的 `Cookie` 完整复制

#### 阿里云盘 refresh_token

1. 浏览器访问 [阿里云盘网页版](https://www.aliyundrive.com/) 并登录
2. 按 `F12` 打开开发者工具 → `Application` 标签页
3. 左侧找到 `Local Storage` → `https://www.aliyundrive.com`
4. 找到 `token` 项，复制 `refresh_token` 的值

#### 百度网盘 Cookie

1. 访问 [百度网盘](https://pan.baidu.com/) 登录
2. F12 → Network → 复制Cookie

#### 天翼云盘配置

1. 浏览器访问 [天翼云盘](https://e.dlife.cn/index.do) ，关闭设备锁
2. 在青龙面板中添加环境变量TY_USERNAME（手机号）
3. 在青龙面板中添加环境变量TY_PASSWD（对应密码）

#### PassNAT 接口密钥获取

1. 浏览器访问 [PassNAT](https://www.passnat.com/) 并登录
2. 进入 **个人中心** → **接口密钥** 页面
3. 点击 **生成密钥** 或复制已有的密钥
4. 将获取到的 `SK_xxxxx` 格式的密钥填入环境变量
5. 多账号用户可生成多个密钥，换行分隔填写

---

## 📝 配置示例

```bash
# 通知配置（推荐Telegram）
TG_BOT_TOKEN=1234567890:AAG9rt-6RDaaX0HBLZQq0laNOh898iFYaRQ
TG_USER_ID=1434078534

# 随机化配置（可选）
RANDOM_SIGNIN=true
MAX_RANDOM_DELAY=3600
```

---

## 🤝 贡献指南

欢迎贡献代码和提出建议！

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

## 📄 免责声明

- 本项目仅供学习交流使用，请勿用于商业用途
- 使用本项目所产生的任何问题，作者不承担任何责任
- 请遵守相关网站的使用条款和法律法规

## 📞 联系方式

- GitHub: [@agluo](https://github.com/agluo)
- Issues: [项目问题反馈](https://github.com/agluo/ql-script-hub/issues)

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源协议。

## ⭐ Star History

如果这个项目对你有帮助，请给个 Star ⭐️

[![Star History Chart](https://api.star-history.com/svg?repos=agluo/ql-script-hub&type=Date)](https://star-history.com/#agluo/ql-script-hub&Date)
