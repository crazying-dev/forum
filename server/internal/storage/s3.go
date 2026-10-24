package storage

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
)

// S3Config SeaweedFS S3 配置。
type S3Config struct {
	Endpoint     string
	Region       string
	Bucket       string
	AccessKey    string
	SecretKey    string
	UsePathStyle bool
}

// S3Provider SeaweedFS S3 提供者。
type S3Provider struct {
	client *s3.Client
	bucket string
}

// NewS3 创建 S3 提供者。
func NewS3(ctx context.Context, cfg S3Config) (*S3Provider, error) {
	if cfg.Bucket == "" || cfg.AccessKey == "" || cfg.SecretKey == "" {
		return nil, fmt.Errorf("S3 配置不完整（bucket/access/secret）")
	}
	region := cfg.Region
	if region == "" {
		region = "us-east-1"
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx,
		awsconfig.WithRegion(region),
		awsconfig.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(cfg.AccessKey, cfg.SecretKey, "")),
	)
	if err != nil {
		return nil, err
	}
	client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		if cfg.Endpoint != "" {
			o.BaseEndpoint = aws.String(strings.TrimRight(cfg.Endpoint, "/"))
		}
		o.UsePathStyle = cfg.UsePathStyle
		o.HTTPClient = newHTTPClient()
	})
	return &S3Provider{client: client, bucket: cfg.Bucket}, nil
}

// newHTTPClient 构造 S3 专用 HTTP 客户端：单请求 30s 超时 + 连接池复用。
// 基于 http.DefaultTransport 克隆，保留 Proxy/HTTP2 等默认行为。
func newHTTPClient() *http.Client {
	transport, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		transport = &http.Transport{}
	}
	t := transport.Clone()
	t.MaxIdleConnsPerHost = 100
	t.IdleConnTimeout = 90 * time.Second
	t.TLSHandshakeTimeout = 10 * time.Second
	return &http.Client{Timeout: 30 * time.Second, Transport: t}
}

// Ping 探测 bucket 是否可访问（HeadBucket；启动/健康检查使用）。
func (p *S3Provider) Ping(ctx context.Context) error {
	if p == nil || p.client == nil {
		return fmt.Errorf("S3 客户端未初始化")
	}
	_, err := p.client.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: aws.String(p.bucket)})
	return err
}

// IsNotFound 判断存储错误是否为“对象不存在”（S3 404/NoSuchKey 等）。
func IsNotFound(err error) bool {
	if err == nil {
		return false
	}
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		switch apiErr.ErrorCode() {
		case "NotFound", "NoSuchKey", "404":
			return true
		}
		// NoSuchBucket 是配置/部署错误，不能当作"对象不存在"（否则会被静默回退掩盖成 404）
		if apiErr.ErrorCode() == "NoSuchBucket" {
			return false
		}
	}
	var respErr *awshttp.ResponseError
	if errors.As(err, &respErr) && respErr.HTTPStatusCode() == http.StatusNotFound {
		return true
	}
	return false
}

func (p *S3Provider) Put(ctx context.Context, key string, data []byte, contentType, cacheControl string) error {
	if key == "" {
		return fmt.Errorf("object key 为空")
	}
	in := &s3.PutObjectInput{
		Bucket:      aws.String(p.bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(data),
		ContentType: aws.String(contentType),
	}
	if cacheControl != "" {
		in.CacheControl = aws.String(cacheControl)
	}
	_, err := p.client.PutObject(ctx, in)
	return err
}

func (p *S3Provider) Get(ctx context.Context, key string) (*Object, error) {
	out, err := p.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(p.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, err
	}
	ct, size := "", int64(0)
	if out.ContentType != nil {
		ct = *out.ContentType
	}
	if out.ContentLength != nil {
		size = *out.ContentLength
	}
	return &Object{Body: out.Body, ContentType: ct, Size: size}, nil
}

func (p *S3Provider) Delete(ctx context.Context, key string) error {
	_, err := p.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(p.bucket),
		Key:    aws.String(key),
	})
	return err
}

func (p *S3Provider) Exists(ctx context.Context, key string) (bool, error) {
	_, err := p.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(p.bucket),
		Key:    aws.String(key),
	})
	if err == nil {
		return true, nil
	}
	if IsNotFound(err) {
		return false, nil
	}
	return false, err
}
