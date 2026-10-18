package handler

import (
	"crypto/tls"
	"net/http/httptest"
	"testing"

	"yj-forum/server/internal/config"
)

func TestAbsoluteMediaURL(t *testing.T) {
	tests := []struct {
		name   string
		cfg    *config.Config
		target string
		host   string
		proto  string
		tls    bool
		public string
		want   string
	}{
		{
			name: "configured public base",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "/ov2/api/media/MD1",
			want: "https://yjlt.top/ov2/api/media/MD1",
		},
		{
			name: "bare configured host gets https",
			cfg:  &config.Config{PublicBaseURL: "yjlt.top"},
			host: "internal:8090", public: "/ov2/api/media/MD1",
			want: "https://yjlt.top/ov2/api/media/MD1",
		},
		{
			name: "loopback config falls back to request origin",
			cfg:  &config.Config{PublicBaseURL: "http://localhost:3000"},
			host: "localhost:3200", proto: "http", public: "/ov2/api/media/MD1",
			want: "http://localhost:3200/ov2/api/media/MD1",
		},
		{
			name: "no config uses forwarded proto and host",
			cfg:  &config.Config{},
			host: "forum.example", proto: "https, http", public: "/ov2/api/media/MD1",
			want: "https://forum.example/ov2/api/media/MD1",
		},
		{
			name: "no config uses tls",
			cfg:  &config.Config{},
			host: "api.example", tls: true, public: "/ov2/api/media/MD1",
			want: "https://api.example/ov2/api/media/MD1",
		},
		{
			name: "already absolute",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "https://cdn.example/ov2/api/media/MD1",
			want: "https://cdn.example/ov2/api/media/MD1",
		},
		{
			name: "empty path",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "",
			want: "",
		},
		{
			name: "nil config uses request origin",
			cfg:  nil,
			host: "forum.example", proto: "http", public: "/ov2/api/media/MD1",
			want: "http://forum.example/ov2/api/media/MD1",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			target := tc.target
			if target == "" {
				target = "http://" + tc.host + "/upload"
			}
			req := httptest.NewRequest("POST", target, nil)
			req.Host = tc.host
			if tc.proto != "" {
				req.Header.Set("X-Forwarded-Proto", tc.proto)
			}
			if tc.tls {
				req.TLS = &tls.ConnectionState{}
			}
			if got := absoluteMediaURL(tc.cfg, req, tc.public); got != tc.want {
				t.Fatalf("absoluteMediaURL() = %q, want %q", got, tc.want)
			}
		})
	}
}
