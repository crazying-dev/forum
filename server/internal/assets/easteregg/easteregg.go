// Package easteregg 内置彩蛋数据：随二进制发布，部署时不再依赖外部 JSON 文件。
package easteregg

import _ "embed"

//go:embed easter_egg.json
var raw []byte

// JSON 返回内置彩蛋 JSON（数组：[{ID,Name,Text}]）。
// 调用方可自行解析；返回的是只读切片，不要修改。
func JSON() []byte {
	return raw
}
