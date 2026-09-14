# ICCPrint

[English README](README.md)

ICCPrint 是一個免費、開源的 Windows **ICC 色彩管理列印工具**。它的目標很簡單：**不用 Photoshop，也能明確指定印表機 ICC / ICM、Rendering Intent 與黑點補償，並在送到 Windows 印表機驅動前完成色彩轉換。**

> **專案狀態：Alpha。** 目前主要以 Epson L15160 + Datacolor / SpyderPRINT RGB 印表機描述檔工作流程開發與測試。其他使用 RGB 輸出 ICC 的 Windows 印表機也可能可用，但各家驅動的私有設定不保證完全一致。

## 為什麼做 ICCPrint？

很多一般印表機驅動雖然有 ICM，但不一定讓使用者明確選擇 ICC 的 Rendering Intent。ICCPrint 直接透過 Pillow / LittleCMS 做色彩轉換，因此可以自己選：

- 感應式 Perceptual
- 相對比色 Relative Colorimetric
- 飽和度 Saturation
- 絕對比色 Absolute Colorimetric
- Black Point Compensation（BPC，黑點補償）

ICCPrint 已經做完色彩轉換後，印表機驅動就應該**關閉額外色彩校正**，避免雙重色彩管理。Epson 驅動通常稱為 `無色彩校正 / No Color Adjustment`。

## 主要功能

- PDF、JPG/JPEG、PNG、TIFF（含多頁）、BMP、WebP
- Word / Excel / PowerPoint：若電腦已安裝 LibreOffice，可先自動轉 PDF
- 選擇任意 RGB 印表機 ICC / ICM
- 四種 ICC Rendering Intent
- Black Point Compensation
- ICC 軟打樣預覽
- Fit / Fill / Actual 100% 三種版面模式
- 圖片內嵌 DPI；沒有 DPI 時可指定 fallback DPI
- A5、A4、A3、A3+、B5、Letter、Legal、4×6、5×7，以及自訂 mm 紙張
- 直向 / 橫向
- 多頁文件預覽切換
- Windows 原生列印視窗與印表機內容
- 文件只在本機處理，不上傳網路

## 最重要的色彩管理原則

ICCPrint 已把來源檔案轉換成你選擇的**印表機 ICC**，所以印表機驅動不可再做第二次色彩管理。

以 Epson 為例，通常需要在驅動中找到類似：

`更多選項 → 色彩校正 → 自訂 → 進階 → 無色彩校正 (No Color Adjustment)`

另外，紙張種類、品質、墨水、紙張與其他驅動設定，都應和建立該 ICC 時一致。

## Windows 快速開始

需求：

- Windows 10 / 11
- 64 位元 Python 3.12 或 3.13
- 一個印表機 ICC / ICM 描述檔
- 選用：LibreOffice（直接開 Office 文件時需要）

下載或 clone 專案後執行：

```bat
install_and_run.bat
```

第一次會建立 `.venv` 並安裝相依套件。之後可以直接執行：

```bat
run.bat
```

也可以手動：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

## 打包成 Windows EXE

先完成第一次安裝，再執行：

```bat
build_exe.bat
```

輸出會在：

```text
dist\ICCPrint\ICCPrint.exe
```

專案也附有 GitHub Actions workflow，可在 GitHub 上手動建立 Windows artifact。

## Fit / Fill / Actual

- **Fit**：完整保留來源內容，等比例縮放到紙張內可容納的最大尺寸。
- **Fill**：填滿整張紙；比例不合時會從中央裁切。
- **Actual 100%**：維持實體尺寸。PDF 使用文件頁面尺寸；圖片使用內嵌 DPI，若沒有 DPI 則使用介面中指定的 fallback DPI。

例如一張 200 × 200 px、254 dpi 的圖片，Actual 會以約 **2 × 2 cm** 顯示與列印，而不是自動放大到 A4。

## ICC 軟打樣

預覽使用 LittleCMS proofing transform，以目前選擇的印表機 ICC、Rendering Intent 與 BPC 模擬輸出，再轉回 sRGB 顯示。

它很適合比較：

- 不同 ICC
- Perceptual / Relative / Saturation / Absolute
- BPC 開關
- Fit / Fill / Actual
- 紙張尺寸、方向與裁切結果

但軟打樣仍然只是近似。螢幕校正、亮度、環境光、紙張白點、墨水、乾燥狀態與印表機驅動設定都會影響實際紙張結果。

## 目前限制

- 目前以 Windows 為主。
- 目前只支援裝置色彩空間為 RGB 的印表機 ICC。
- PDF 會先由 PDFium 點陣化，再做 ICC 轉換，因此 PDF 的文字與向量最後會成為像素輸出。
- Windows 沒有跨廠牌、跨驅動版本的標準 API 可以可靠地強制設定 Epson 等廠商的私有色彩選項，因此 `No Color Adjustment` 仍需使用者在印表機內容中確認。
- 預覽目前以整張紙為基準；真正的不可列印邊界由印表機驅動控制。

## 文件

- [Windows 安裝說明](docs/INSTALL_WINDOWS.md)
- [ICC 色彩工作流程](docs/COLOR_MANAGEMENT.md)
- [程式架構](docs/ARCHITECTURE.md)
- [如何貢獻](CONTRIBUTING.md)
- [第三方授權](THIRD_PARTY_NOTICES.md)

## 開發與測試

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions 會在支援的 Windows / Python 版本上做基本安裝、語法編譯與單元測試。

## License

ICCPrint 自有原始碼採 [MIT License](LICENSE)。第三方套件仍依各自授權條款使用，詳見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 商標聲明

Epson、Datacolor、SpyderPRINT、Adobe、Windows 等名稱與商標均屬其各自權利人所有。ICCPrint 是獨立的開源專案，與上述公司沒有隸屬或背書關係。
