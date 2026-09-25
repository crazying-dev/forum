# 罗小黑主题鼠标指针

中文 | [English](/WIKI/Personal/mouse/Liunx?l=EN)

![Banner](https://img.crazying-dev.top/text/one/mouse/Liunx/banner.png)

## 关于项目

- **原作者**：[哔哩哔哩 @1013625945（漓翎_cub）](https://space.bilibili.com/1013625945)
- 移植者：[GitHub @Tseshongfeeshur（Ryan）](https://github.com/Tseshongfeeshur)

由于截至项目发布（2025.12.6），原作者仅为 Windows 和 MacOS 平台提供适配，尚未提供 [GNU](https://www.gnu.org/)/[Linux](https://kernel.org/) 版本，遂将其移植为适用于大多数桌面环境的 [XDG 主题包](https://specifications.freedesktop.org/icon-theme/latest/)，以供 [GNU](https://www.gnu.org/)/[Linux](https://kernel.org/) 用户使用。**特别感谢原作者的付出和努力，否则该移植项目不可能出现，我们也不可能用到如此精美的鼠标指针。**

## 项目内容

- 以在[《罗小黑战记》](https://www.bilibili.com/bangumi/play/ep32374)系列作品中出场的角色“罗小黑”为原型，由[**漓翎_cub**](https://space.bilibili.com/1013625945)设计并制作
- **大部分**为动态图标
- 支持 **24 / 32 / 48 / 64 / 96 / 128 / 192 / 256 / 512** 多分辨率

## 适用平台

- [GNU](https://www.gnu.org/)/[Linux](https://kernel.org/) 平台所有支持 [XDG 主题包](https://specifications.freedesktop.org/icon-theme/latest/)的桌面环境
  - 在 [KDE Plasma](https://kde.org/plasma-desktop/)、[GNOME](https://www.gnome.org/) 通过测试，表现良好

## 安装方式

推荐安装预构建包，因此暂不提供自行构建安装步骤，仅提供使用预构建包安装的步骤。

若希望自行构建安装，请使用 `sources` 目录内的构建脚本。该脚本可直接生成主题文件夹。Arch Linux 用户可以安装名为 `hei-cursors-git` 的 AUR 包。

### Arch Linux

#### 使用 AUR 助手

```zsh
paru -S hei-cursors-bin
```

**或**选择其他您喜欢的 AUR 助手：
```zsh
yay -S hei-cursors-bin
```

#### 手动安装 AUR 包

```zsh
sudo pacman -S --needed base-devel
git clone https://aur.archlinux.org/hei-cursors-bin.git
cd hei-cursors-bin
makepkg -si
```

**或**参见下文手动安装 **（不建议，会导致 `pacman` 无法追踪该包）**。

### 其他发行版（手动安装）

1. 安装 `curl` 和 `tar`
   - Debian
     ```zsh
     sudo apt update
     sudo apt install curl tar
     ```

   - Fedora
     ```zsh
     sudo dnf install curl tar
     ```
   - Arch Linux
     ```zsh
     sudo pacman -S curl tar
     ```

2. 为**当前用户**安装：
   ```zsh
   curl -L "https://github.com/Tseshongfeeshur/hei-cursors/releases/latest/download/hei-cursors.tar.gz" -o hei-cursors.tar.gz
   tar -xzf hei-cursors.tar.gz
   mkdir -p ~/.local/share/icons/
   mv ./hei_cursors ~/.local/share/icons/
   ```

   **或**为**所有用户**安装 **（不建议）**：
   ```zsh
   curl -L "https://github.com/Tseshongfeeshur/hei-cursors/releases/latest/download/hei-cursors.tar.gz" -o hei-cursors.tar.gz
   tar -xzf hei-cursors.tar.gz
   sudo mkdir -p /usr/share/icons/
   sudo mv ./hei_cursors /usr/share/icons/
   ```

## 应用方式

### KDE Plasma

1. 导航至**系统设置 → 外观和样式 → 颜色和主题 → 光标**，或：
   ```zsh
   systemsettings kcm_cursortheme
   ```

2. 单击“**罗小黑**”光标样式后单击窗口右下角“**应用**”
3. 在窗口上方选择观感舒适的光标大小

### GNOME

1. 安装 `gnome-tweaks`
   - Debian
     ```zsh
     sudo apt update
     sudo apt install gnome-tweaks
     ```

   - Fedora
     ```zsh
     sudo dnf install gnome-tweaks
     ```

   - Arch Linux
     ```zsh
     sudo pacman -S gnome-tweaks
     ```

2. 导航至**优化 → 外观 → 光标**
3. 单击下拉菜单，选择“**Hei_cursor**”光标样式
4. 选择观感舒适的光标大小：
   ```zsh
   gsettings set org.gnome.desktop.interface cursor-size $px
   # 将“$px”改为您需要的像素值，如 48
   ```

### 其他

由于桌面环境 / 窗口管理器种类繁多，请查看其他平台对应文档，恕不一一赘述。

## 鸣谢

- **原作者**[**漓翎_cub**](https://space.bilibili.com/1013625945)，没有他的付出，就没有这个项目
- `xorg-xcursorgen`，它为多分辨率图标的生成提供了很便捷的方式
