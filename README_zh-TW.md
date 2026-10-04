# ICCPrint

[English](README.md)

ICCPrint 是在 Windows 本機執行的 **ICC 色彩管理列印工具，不必使用 Photoshop**。可指定 RGB 印表機描述檔與 Rendering Intent，比較來源色彩預覽及 ICC 軟打樣，再透過 Windows 印表機驅動送出列印。主要介面為繁體中文。

**0.3.0 目前仍是開發版本。** 自動測試涵蓋色彩驗證、點陣化、版面、工作準備及打包，不能視為印表機認證或色準保證。Epson L15160 搭配 Datacolor/SpyderPRINT RGB 描述檔是專案原始參考情境；本版本公開發行前仍須留下 Windows、驅動與實體列印驗收紀錄。

## 快速開始

### 可攜式 Windows 套件

完整解壓縮版本 ZIP，執行 `ICCPrint/ICCPrint.exe`，**不必安裝 Python**。請保留旁邊的 `_internal`、文件與授權資料，不要只複製 EXE 或在 ZIP 內直接執行。

原始碼儲存庫不含預先建好的 EXE。GitHub Actions 的 Windows 工作流程可手動建立測試套件，也會對符合條件的 pull request 執行；不會自動發佈 release 或 tag。

### 從原始碼執行

使用 Windows 10/11 x64 與 64 位元 Python 3.12 或 3.13，執行：

```bat
install_and_run.bat
```

首次安裝後用 `run.bat` 啟動。也可手動安裝：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

`requirements-lock.txt` 固定測試用相依版本。列印需要原廠 Windows 驅動與對應的 RGB 印表機輸出 ICC/ICM。Office 轉檔需另裝 LibreOffice；套件不內附 LibreOffice、印表機驅動或 ICC 描述檔。

## 建議操作順序

1. 加入圖片、PDF 或支援的 Office 文件；讀取與轉換在背景處理
2. 選擇符合「印表機、墨水、紙張」的 RGB **輸出裝置**描述檔。螢幕/sRGB 描述檔不能當成印表機描述檔
3. 設定紙張、方向與 Fit／Fill／Actual，切換來源色彩預覽及 ICC 軟打樣，留意解析度與裁切提示
4. 選擇 Intent 與黑點補償。新安裝預設為「相對比色＋BPC」，可將常用應用程式設定存成具名預設
5. 在原廠驅動內容中關閉額外色彩校正，並匹配建立 ICC 時的紙材與品質設定。每次啟動都要重新確認勾選，預設組不會保存這項確認
6. 確認列印前檢查與 Windows 原生列印視窗。選定頁面會先完整點陣化、轉色並準備到暫存磁碟，再啟動印表機工作；先印一頁實體測試

Epson 常見路徑類似「列印內容 → 更多選項 → 色彩校正 → 自訂 → 進階 → 無色彩校正」，實際名稱依驅動而異。ICCPrint 無法替你強制修改這類廠商專屬設定。

## 主要功能

- PDF、JPEG、PNG、多頁 TIFF、BMP、WebP；Office 文件可透過 LibreOffice 轉 PDF
- 驗證來源 ICC、白底合成透明區域；無標記的 RGB 內容明確假設為 sRGB
- 驗證 RGB 印表機輸出 ICC 與 Intent；拒絕螢幕/sRGB 及 CMYK 輸出描述檔
- Perceptual／Relative Colorimetric／Saturation／Absolute Colorimetric，搭配可選黑點補償
- 背景匯入、預覽與工作準備；忽略過時結果，文件排序、直接跳頁、來源／軟打樣比較
- Fit／Fill／Actual 100%、內嵌 DPI 與備用 DPI、標準／自訂紙張、直／橫向
- 具名本機預設、列印前檢查、解析度及裁切提示
- 所有頁面準備完成才送出、限制點陣配置、暫存清理與合作式取消
- Windows 原生列印視窗、頁面範圍及份數／逐份列印處理
- 版本化可攜套件、EXE 版本資訊、相依授權、檔案清單及 SHA-256 校驗值
- 文件在本機處理，不會上傳至文件處理服務

## 必須知道的限制

- Fit 保留完整內容；Fill 會置中裁切；Actual 保持實體尺寸，可能超出紙張。圖片使用內嵌或備用 DPI，PDF 使用頁面實體尺寸
- PDF 經 PDFium 點陣化後以 sRGB 影像處理；文字與向量會變成像素，不是保留向量的印前或 RIP 流程
- 軟打樣是轉回 sRGB 的模擬，不會自動套用螢幕 ICC，不能取代螢幕校正、受控觀察環境與實際試印
- 預覽與輸出使用全紙座標；硬體不可列印邊界仍可能裁切，並不保證無邊框
- 取消只能停止尚未送出的頁面，無法收回已交給驅動或印表機的紙張。「已送至佇列」不等於實體列印完成
- 目前每頁上限為一億像素、單邊 32,768 像素；超出時會拒絕並提示降低 DPI 或縮小來源

## 建置 Windows 套件

在 x64 Windows 與 Python 3.12／3.13 執行：

```bat
build_exe.bat
```

不必先建立開發用 `.venv`。建置程式會重建獨立環境、安裝固定版本、執行測試、產生並測試 EXE、收集文件與授權，輸出：

```text
dist/ICCPrint/ICCPrint.exe
dist/ICCPrint/BUILD_MANIFEST.json
dist/ICCPrint-0.3.0-Windows-x64.zip
dist/ICCPrint-0.3.0-Windows-x64.zip.sha256
```

CI 在 Ubuntu／Windows 搭配 Python 3.12／3.13 執行無視窗測試；Windows 打包還會解壓縮、核對清單並測試執行檔。這些檢查不包含實體印表機。固定相依與 ZIP 時戳可改善重建一致性，但不保證不同 Windows／Python 修補版本的原生 EXE 位元完全一致。

## 文件

- [操作指南](docs/USER_GUIDE.md)
- [Windows 安裝與建置](docs/INSTALL_WINDOWS.md)
- [色彩管理流程](docs/COLOR_MANAGEMENT.md)
- [疑難排解](docs/TROUBLESHOOTING.md)
- [架構](docs/ARCHITECTURE.md)
- [貢獻與測試](CONTRIBUTING.md)
- [發行驗收清單](docs/RELEASE_CHECKLIST.md)
- [第三方授權](THIRD_PARTY_NOTICES.md)、[相依原始碼](docs/DEPENDENCY_SOURCES.md)
- [更新紀錄](CHANGELOG.md)

## 授權與商標

ICCPrint 原始碼採 [MIT 授權](LICENSE)，相依元件保留各自授權；重新散佈二進位套件前仍須完成第三方授權及對應原始碼義務檢查。Epson、Datacolor、SpyderPRINT、Adobe、Windows 等名稱屬各公司商標；本專案與上述公司無隸屬或背書關係。
