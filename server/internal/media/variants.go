package media

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"math"
	"strconv"

	"golang.org/x/image/draw"
)

// variantWidths 上传时预生成的变体宽度（px）；读路径仅接受这两个值。
var variantWidths = []int{480, 1280}

// variantJPEGQuality 变体 JPEG 编码质量。
const variantJPEGQuality = 82

// variantObject 待写入存储的变体对象（尚未绑定 media_id）。
type variantObject struct {
	Variant   string // w480 / w1280
	ObjectKey string // scene/YYYY/MM/<id>@480.jpg
	Width     int
	Height    int
	Mime      string
	Data      []byte
	SHA256    string
}

// buildVariants 生成等比缩放变体（JPEG，质量 82）：
//   - 原图宽度 <= 目标宽度时跳过该档（不放大）；
//   - 仅由调用方对 JPEG/PNG 源图调用（GIF/WebP 在 prepareUpload 层已拦截）；
//     调色板 PNG 也照常缩放（透明区域先铺白底）。
//   - dir 与主对象共用同一个 YYYY/MM 前缀，避免跨月边界时前缀错位。
func buildVariants(img image.Image, id, scene, dir string) ([]variantObject, error) {
	if img == nil {
		return nil, nil
	}
	b := img.Bounds()
	srcW, srcH := b.Dx(), b.Dy()
	if srcW <= 0 || srcH <= 0 {
		return nil, fmt.Errorf("图片尺寸无效")
	}
	prefix := scene + "/" + dir + "/"
	out := make([]variantObject, 0, len(variantWidths))
	for _, w := range variantWidths {
		if srcW <= w {
			continue // 原图不宽于目标：无需放大
		}
		h := int(math.Round(float64(srcH) * float64(w) / float64(srcW)))
		if h < 1 {
			h = 1
		}
		dst := image.NewRGBA(image.Rect(0, 0, w, h))
		// JPEG 无透明通道：先铺白底，避免 PNG 透明区域变黑
		draw.Draw(dst, dst.Bounds(), image.NewUniform(color.White), image.Point{}, draw.Src)
		draw.CatmullRom.Scale(dst, dst.Bounds(), img, b, draw.Over, nil)
		var buf bytes.Buffer
		if err := jpeg.Encode(&buf, dst, &jpeg.Options{Quality: variantJPEGQuality}); err != nil {
			return nil, fmt.Errorf("变体编码失败: %w", err)
		}
		digest := sha256.Sum256(buf.Bytes())
		out = append(out, variantObject{
			Variant:   variantName(w),
			ObjectKey: prefix + id + "@" + strconv.Itoa(w) + ".jpg",
			Width:     w,
			Height:    h,
			Mime:      "image/jpeg",
			Data:      buf.Bytes(),
			SHA256:    hex.EncodeToString(digest[:]),
		})
	}
	return out, nil
}

// variantName 宽度 -> 变体名（w480）。
func variantName(width int) string {
	return "w" + strconv.Itoa(width)
}
