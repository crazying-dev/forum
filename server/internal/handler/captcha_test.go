package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	altchalib "github.com/altcha-org/altcha-lib-go/v2"
	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/altcha"
)

func newCaptchaTestRouter(svc *altcha.Service) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	RegisterCaptchaRoutes(r.Group("/ov2/api"), NewCaptchaHandler(svc))
	return r
}

func doCaptchaJSON(r *gin.Engine, method, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestCaptchaConfigAndChallengeRoutes(t *testing.T) {
	svc := altcha.New(nil, altcha.Config{Enabled: true, HMACKey: "test-key", Cost: 10, Expires: time.Minute})
	r := newCaptchaTestRouter(svc)

	w := doCaptchaJSON(r, http.MethodGet, "/ov2/api/captcha/config", "")
	if w.Code != http.StatusOK {
		t.Fatalf("config status = %d, want 200", w.Code)
	}
	var cfgResp struct {
		Success   bool   `json:"success"`
		Enabled   bool   `json:"enabled"`
		Algorithm string `json:"algorithm"`
		Cost      int    `json:"cost"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &cfgResp); err != nil {
		t.Fatalf("decode config: %v", err)
	}
	if !cfgResp.Success || !cfgResp.Enabled || cfgResp.Algorithm != altcha.DefaultAlgorithm || cfgResp.Cost != 10 {
		t.Fatalf("unexpected config: %+v", cfgResp)
	}

	w = doCaptchaJSON(r, http.MethodGet, "/ov2/api/captcha/challenge", "")
	if w.Code != http.StatusOK {
		t.Fatalf("challenge status = %d, want 200", w.Code)
	}
	var challenge altchalib.Challenge
	if err := json.Unmarshal(w.Body.Bytes(), &challenge); err != nil {
		t.Fatalf("decode challenge: %v", err)
	}
	if challenge.Parameters.Nonce == "" || challenge.Signature == "" {
		t.Fatalf("unexpected challenge: %+v", challenge)
	}
}

func TestCaptchaRoutesDisabled(t *testing.T) {
	r := newCaptchaTestRouter(altcha.New(nil, altcha.Config{Enabled: false}))

	w := doCaptchaJSON(r, http.MethodGet, "/ov2/api/captcha/config", "")
	if w.Code != http.StatusOK || !strings.Contains(w.Body.String(), `"enabled":false`) {
		t.Fatalf("disabled config = %d %s", w.Code, w.Body.String())
	}
	if w := doCaptchaJSON(r, http.MethodGet, "/ov2/api/captcha/challenge", ""); w.Code != http.StatusNotFound {
		t.Fatalf("disabled challenge status = %d, want 404", w.Code)
	}
	if w := doCaptchaJSON(r, http.MethodPost, "/ov2/api/captcha/verify", `{"altcha":"x"}`); w.Code != http.StatusNotFound {
		t.Fatalf("disabled verify status = %d, want 404", w.Code)
	}
}

func TestCaptchaVerifyRejectsBadPayload(t *testing.T) {
	r := newCaptchaTestRouter(altcha.New(nil, altcha.Config{Enabled: true, HMACKey: "test-key", Cost: 10}))

	w := doCaptchaJSON(r, http.MethodPost, "/ov2/api/captcha/verify", `{"altcha":"not-base64!"}`)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("verify status = %d, want 400", w.Code)
	}
	if !strings.Contains(w.Body.String(), "CAPTCHA_REQUIRED") {
		t.Fatalf("verify body = %s, want CAPTCHA_REQUIRED", w.Body.String())
	}
}

func TestVerifyRequestBehavior(t *testing.T) {
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	c.Request = httptest.NewRequest(http.MethodPost, "/", nil)

	// 未注入 / 未启用：跳过。
	if !VerifyRequest(c, nil, "", "") {
		t.Fatal("nil service must skip ALTCHA")
	}
	if !VerifyRequest(c, altcha.New(nil, altcha.Config{Enabled: false}), "", "") {
		t.Fatal("disabled service must skip ALTCHA")
	}

	// 启用但无 proof：fail-closed。
	svc := altcha.New(nil, altcha.Config{Enabled: true, HMACKey: "test-key"})
	if VerifyRequest(c, svc, "", "") {
		t.Fatal("missing proof must be rejected")
	}

	// 有效 grant 通过，篡改后拒绝。
	grant, err := svc.Grant(c.ClientIP())
	if err != nil {
		t.Fatalf("Grant() error = %v", err)
	}
	if !VerifyRequest(c, svc, "", grant) {
		t.Fatal("valid grant must pass")
	}
	if VerifyRequest(c, svc, "", grant+"x") {
		t.Fatal("tampered grant must be rejected")
	}
}
