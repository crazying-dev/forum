你想了解CSS（层叠样式表）的常用核心内容，我会从新手易理解的角度，梳理CSS最常用的知识点和用法，帮你快速掌握日常开发中高频用到的内容。

### 一、CSS 基础语法与引入方式
#### 1. 基础语法
CSS 由**选择器**、**属性**和**值**组成，基本结构:
```css
/* 选择器 { 属性: 值; 属性: 值; } */
p {
  color: red; /* 文字颜色 */
  font-size: 16px; /* 字体大小 */
}
```

#### 2. 三种引入方式（日常开发高频）
| 引入方式 | 写法示例 | 适用场景 |
|----------|----------|----------|
| 行内样式 | `<div style="color: blue;">内容</div>` | 临时样式、单个元素特殊样式 |
| 内部样式 | `<style> div { color: blue; } </style>` | 单个页面的样式（写在HTML的`<head>`中） |
| 外部样式 | `<link rel="stylesheet" href="style.css">` | 多页面共用样式（最推荐） |

### 二、常用选择器（核心）
选择器用于选中要样式化的HTML元素，以下是日常开发80%场景会用到的:
```css
/* 1. 元素选择器:选中所有对应标签 */
div { background: #f5f5f5; }

/* 2. 类选择器（最常用）:选中class="box"的元素 */
.box { width: 200px; height: 200px; }

/* 3. ID选择器:选中id="header"的元素（唯一） */
#header { height: 80px; }

/* 4. 后代选择器:选中.box内部的p标签 */
.box p { color: #333; }

/* 5. 伪类选择器（高频）:如:hover（鼠标悬浮）、:active（点击） */
a:hover { color: orange; } /* 链接悬浮变色 */
button:active { background: #ccc; } /* 按钮点击效果 */

/* 6. 通配符选择器:选中所有元素（常用于重置默认样式） */
* { margin: 0; padding: 0; box-sizing: border-box; }
```

### 三、常用样式属性（按场景分类）
#### 1. 文本样式（高频）
```css
.text {
  font-size: 14px; /* 字体大小，单位:px/rem/em */
  color: #666; /* 文字颜色（十六进制/ rgb/ 英文） */
  font-weight: 400; /* 字体粗细:400(正常)/700(粗体) */
  text-align: center; /* 文本对齐:left/center/right */
  line-height: 1.5; /* 行高（控制文字行间距，常用1.5-2） */
  text-decoration: none; /* 去除下划线（常用于a标签） */
  overflow: hidden; /* 超出隐藏 */
  text-overflow: ellipsis; /* 文字超出显示省略号 */
  white-space: nowrap; /* 强制不换行（配合上两行实现单行省略） */
}
```

#### 2. 盒子模型（核心中的核心）
所有HTML元素都可视为“盒子”，由`margin`（外边距）、`border`（边框）、`padding`（内边距）、`content`（内容）组成:
```css
.box {
  width: 300px; /* 宽度 */
  height: 200px; /* 高度 */
  margin: 10px auto; /* 外边距:上下10px，左右自动（居中） */
  padding: 15px; /* 内边距:上下左右15px */
  border: 1px solid #ddd; /* 边框:1px 实线 灰色 */
  border-radius: 8px; /* 圆角（常用，实现圆角盒子/圆形） */
  box-sizing: border-box; /* 关键:让width/height包含padding和border，避免盒子变形 */
  background: #fff; /* 背景色 */
  background-image: url("bg.jpg"); /* 背景图 */
  background-size: cover; /* 背景图覆盖盒子 */
}
```

#### 3. 布局相关（日常开发核心）
##### （1）Flex 弹性布局（最常用，适配性好）
用于快速实现水平/垂直居中、均分、对齐等布局:
```css
/* 父元素设置flex */
.flex-container {
  display: flex; /* 开启flex布局 */
  justify-content: space-between; /* 水平对齐:space-between(两端对齐)/center(居中)/space-around(均匀分布) */
  align-items: center; /* 垂直对齐:center(居中)/flex-start(顶部)/flex-end(底部) */
  flex-wrap: wrap; /* 自动换行（子元素超出父元素时） */
}
/* 子元素可选设置 */
.flex-item {
  flex: 1; /* 子元素均分父元素宽度（常用） */
  margin: 0 5px;
}
```

##### （2）定位（position）
用于控制元素的位置，高频场景:弹窗、悬浮导航、固定头部等:
```css
/* 相对定位:相对于自身原位置偏移，不脱离文档流 */
.relative { position: relative; top: 10px; left: 20px; }

/* 绝对定位:相对于最近的已定位父元素偏移，脱离文档流 */
.absolute { position: absolute; top: 0; right: 0; }

/* 固定定位:相对于浏览器窗口固定，脱离文档流（如固定导航栏） */
.fixed { position: fixed; top: 0; left: 0; width: 100%; z-index: 999; }

/* z-index:控制层级，数值越大越在上层（需配合position使用） */
```

#### 4. 显示与隐藏
```css
/* 隐藏元素（不占空间） */
.hide { display: none; }

/* 隐藏元素（占空间，仅视觉隐藏） */
.invisible { visibility: hidden; }

/* 超出部分隐藏（常用，如盒子内容溢出） */
.overflow-hidden { overflow: hidden; }
```

### 四、响应式相关（适配不同设备）
通过媒体查询适配手机、平板、电脑等不同屏幕:
```css
/* 屏幕宽度≤768px（手机端）时生效 */
@media (max-width: 768px) {
  .box {
    width: 100%; /* 宽度占满屏幕 */
    padding: 10px;
  }
  .flex-container {
    flex-direction: column; /* 子元素垂直排列 */
  }
}
```

### 五、常用技巧/重置样式
新手常踩坑的默认样式重置（消除浏览器默认差异）:
```css
/* 通用重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
/* 去除列表默认样式 */
ul, li { list-style: none; }
/* 去除a标签下划线 */
a { text-decoration: none; color: #333; }
/* 去除按钮默认样式 */
button { border: none; outline: none; cursor: pointer; }
```

### 总结
CSS 常用内容可归纳为3个核心关键点:
1. **基础层**:掌握选择器（类选择器、后代选择器、伪类）和引入方式，能精准选中要样式化的元素；
2. **样式层**:重点掌握文本样式、盒子模型（margin/padding/border/box-sizing），这是控制元素外观的基础；
3. **布局层**:Flex 布局是日常开发的核心，配合 position 定位、响应式媒体查询，能实现绝大多数页面布局需求。

这些内容覆盖了前端开发中 90% 以上的 CSS 高频场景，先掌握这些，再逐步拓展动画、渐变、Grid 布局等进阶内容即可。