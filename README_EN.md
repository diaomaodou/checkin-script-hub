# QL Script Hub

> 🚀 Personal QingLong script hub - one-stop solution for check-ins and monitoring

[中文说明](README.md) | English

[![GitHub stars](https://img.shields.io/github/stars/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/network)
[![GitHub issues](https://img.shields.io/github/issues/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/issues)
[![License](https://img.shields.io/github/license/agluo/ql-script-hub?style=flat-square)](https://github.com/agluo/ql-script-hub/blob/main/LICENSE)

## 📋 Overview

QL Script Hub is a script collection built for QingLong Panel, providing automation for daily check-ins, monitoring, and similar repetitive tasks. The scripts are intended to be easy to deploy and maintain.

## ✨ Features

- 🎯 **Diverse scripts** - Covers check-ins, notifications, and other automation scenarios
- 🔧 **Easy configuration** - Unified environment-variable based setup
- 📦 **Modular design** - Clear file structure for maintenance and extension
- 🛡️ **Reliable** - Scripts are organized for practical day-to-day usage
- 📝 **Documented** - Includes setup notes and parameter descriptions
- 🔄 **Continuously updated** - Easy to expand with more services over time

## 📁 Project Structure

```text
ql-script-hub/
├── README.md                    # Chinese README
├── README_EN.md                 # English README
├── LICENSE                      # License
├── aliyunpan_checkin.py         # Aliyun Drive check-in
├── baiduwangpan_checkin.py      # Baidu Netdisk check-in
├── quark_signin.py              # Quark Drive sign-in
├── ty_netdisk_checkin.py        # Tianyi Cloud Drive sign-in
├── passnat_checkin.py           # PassNAT sign-in
├── tsthb_checkin.py             # Tastien Burger sign-in
└── archive/                     # Archived scripts (no longer maintained)
    └── leaflow_checkin.py       # Leaflow sign-in
```

## 🚀 Quick Start

### Requirements

- QingLong Panel 2.10+
- Node.js 14+

### Installation

1. **Pull the repository**

   ```bash
   # Add this repository in QingLong subscription management
   # Subscription URL: https://github.com/agluo/ql-script-hub.git
   ```

   <img width="774" height="1112" alt="image" src="https://github.com/user-attachments/assets/de6cf07f-7af2-42b9-8321-c2ccc542820b" />

2. **Configure environment variables**

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `TG_BOT_TOKEN` | Telegram bot token | Recommended | `1234567890:AAG9rt-6RDaaX0HBLZQq0laNOh898iFYaRQ` | See instructions below |
| `TG_USER_ID` | Telegram user ID | Recommended | `1434078534` | See instructions below |
| `PUSH_KEY` | ServerChan push key | Optional | `SCTxxxxxxxxxxxxxxxxxxxxx` | For WeChat push via `sct.ftqq.com` |
| `PUSH_PLUS_TOKEN` | Push+ token | Optional | `xxxxxxxxxxxxxxxxxx` | For WeChat push via `pushplus.plus` |
| `DD_BOT_TOKEN` | DingTalk bot token | Optional | `xxxxxxxxxxxxxxxxxx` | DingTalk group bot |
| `DD_BOT_SECRET` | DingTalk bot secret | Optional | `xxxxxxxxxxxxxxxxxx` | Optional bot signing secret |
| `BARK_PUSH` | Bark push URL | Optional | `https://api.day.app/your_key/` | Bark push for iOS |

#### ☁️ Quark Drive

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `QUARK_COOKIE` | Quark Drive cookie | **Required** | `cookie1\ncookie2` | Separate multiple accounts with new lines |

#### ☁️ Aliyun Drive

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `ALIYUN_REFRESH_TOKEN` | Aliyun Drive `refresh_token` | **Required** | `crsh166bdfde4751a4c0...` | Separate multiple accounts with new lines |
| `AUTO_UPDATE_TOKEN` | Auto update token | Optional | `true` | Default is `true` |
| `PRIVACY_MODE` | Privacy mode | Optional | `true` | Default is `true`, masks sensitive values |

#### 🍔 Tastien Burger

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `tsthbck` | Tastien Burger `user-token` | **Required** | `xxxxx` | Captured from the WeChat mini program, one account per line |

#### ☁️ Baidu Netdisk

| Variable | Description | Example |
|--------|------|------|
| `BAIDU_COOKIE` | Website cookie | `BDUSS=xxx; STOKEN=xxx...` |
| `PRIVACY_MODE` | Privacy mode | `true` |

#### ☁️ Tianyi Cloud Drive

| Variable | Description | Example |
|--------|------|------|
| `TY_USERNAME` | Login phone number | `13812345678` |
| `TY_PASSWORD` | Login password | `password1` |

#### 🌐 PassNAT

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `PASSNAT_SK` | PassNAT API key | **Required** | `sk_xxxxx` | Separate multiple accounts with new lines |

#### ⏰ Randomization Settings (shared by all scripts)

| Variable | Description | Required | Example | Notes |
|--------|------|----------|--------|------|
| `RANDOM_SIGNIN` | Enable random sign-in | Optional | `true` | `true` to enable, `false` to disable |
| `MAX_RANDOM_DELAY` | Random delay window in seconds | Optional | `3600` | `3600` = 1 hour, `1800` = 30 minutes |

---

## 🔧 How to Obtain Required Values

### 📱 Telegram Setup
1. **Create a bot**: Chat with [@BotFather](https://t.me/botfather) and send `/newbot`
2. **Get the token**: After creation, BotFather returns your `TG_BOT_TOKEN`
3. **Get user ID**: Chat with [@userinfobot](https://t.me/userinfobot) to get `TG_USER_ID`

### 🍪 Cookie / Credential Collection

#### Quark Drive cookie
1. Visit [Quark Drive](https://pan.quark.cn/) and sign in
2. Open developer tools with `F12` → `Network` → refresh the page
3. Copy the full `Cookie` value from request headers

#### Aliyun Drive `refresh_token`
1. Visit [Aliyun Drive Web](https://www.aliyundrive.com/) and sign in
2. Press `F12` → open the `Application` tab
3. Find `Local Storage` → `https://www.aliyundrive.com`
4. Locate `token` and copy the `refresh_token` value

#### Baidu Netdisk cookie
1. Visit [Baidu Netdisk](https://pan.baidu.com/) and sign in
2. Press `F12` → `Network` → copy the cookie

#### Tianyi Cloud Drive configuration
1. Visit [Tianyi Cloud Drive](https://e.dlife.cn/index.do) and disable device lock
2. Add `TY_USERNAME` in QingLong Panel
3. Add `TY_PASSWD` in QingLong Panel

#### PassNAT API key
1. Visit [PassNAT](https://www.passnat.com/) and sign in
2. Go to **Account Center** → **API Keys**
3. Click **Generate Key** or copy an existing key
4. Fill the `SK_xxxxx`-formatted key into the environment variable
5. For multiple accounts, generate multiple keys and separate them with new lines

---

## 📝 Configuration Example

```bash
# Notifications (Telegram recommended)
TG_BOT_TOKEN=1234567890:AAG9rt-6RDaaX0HBLZQq0laNOh898iFYaRQ
TG_USER_ID=1434078534

# Randomization settings (optional)
RANDOM_SIGNIN=true
MAX_RANDOM_DELAY=3600
```

---

## 🤝 Contributing

Contributions and suggestions are welcome.

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 Disclaimer

- This project is for learning and personal communication only
- The author is not responsible for any issues caused by using this project
- Please comply with the target websites' terms of service and local laws

## 📞 Contact

- GitHub: [@agluo](https://github.com/agluo)
- Issues: [Project issue tracker](https://github.com/agluo/ql-script-hub/issues)

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## ⭐ Star History

If this project helps you, a star is appreciated ⭐️

[![Star History Chart](https://api.star-history.com/svg?repos=agluo/ql-script-hub&type=Date)](https://star-history.com/#agluo/ql-script-hub&Date)
