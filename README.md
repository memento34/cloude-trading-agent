# 🤖 Multi-Agent Trading System

OKX üzerinde çalışan, 6 bağımsız trading agent + 3 oracle + eliminator içeren
evrimsel paper trading sistemi.

---

## 🚀 Hızlı Kurulum (Railway + GitHub)

### 1. GitHub'a Yükle
```
1. GitHub'da yeni bir PRIVATE repo aç (örn: "my-trading-bot")
2. Bu klasördeki TÜM dosyaları o repoya yükle
3. .env dosyasını YÜKLEME (zaten .gitignore'da)
```

### 2. Railway'de Kur
```
1. railway.app → New Project → Deploy from GitHub
2. Repoyu seç
3. Settings → Environment Variables bölümüne git
4. Aşağıdaki değişkenleri gir:
```

### 3. Railway Environment Variables
| Değişken | Değer |
|---|---|
| `OKX_API_KEY` | OKX sub-account API key'in |
| `OKX_SECRET_KEY` | OKX secret key'in |
| `OKX_PASSPHRASE` | OKX passphrase'in |
| `PAPER_TRADING` | `True` |
| `INITIAL_BALANCE` | `500` |
| `DASHBOARD_PASSWORD` | Seçtiğin şifre |
| `CMC_API_KEY` | CoinMarketCap API key (opsiyonel) |

### 4. Deploy Et
```
Railway otomatik deploy eder.
Logs sekmesinden sistemi izleyebilirsin.
Railway'in verdiği URL + ?pwd=ŞIFREN ile dashboard'a erişirsin.
```

---

## 🤖 Agent Açıklamaları

| Agent | Strateji | Stop Loss | Take Profit |
|---|---|---|---|
| **Sentinel** | Güçlü trend sinyalleri | %1.5 | %2.5 |
| **Momentum** | Hype + teknik onay | %2.0 | %4.0 |
| **Bouncer** | RSI dip alımları | %2.0 | %2.0 |
| **Breakout** | Bollinger kırılmaları | %1.8 | %4.0 |
| **Scalper** | BTC/ETH/SOL hızlı işlem | %0.8 | %1.0 |
| **Synthesizer** | 2+ oracle onayı | %2.0 | %3.0 |

---

## 📊 Dashboard Özellikleri
- Gerçek zamanlı agent sıralaması ve skorlar
- Açık pozisyonlar
- Son sinyaller (Teknik + Hype + Rejim)
- Eleme logu
- Risk durumu

---

## ⚠️ Önemli Notlar
- **PAPER_TRADING=True** ile gerçek işlem AÇILMAZ
- OKX API key'i sadece okuma (read-only) iznine sahip olabilir
- Günlük %8 kayıp → sistem otomatik durur
- 3 gün üst üste zarar → agent dondurulur
- Haftalık en kötü performans → bütçe azaltılır veya elinir
