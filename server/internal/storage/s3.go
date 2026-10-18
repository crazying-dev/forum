package storage

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
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
	})
	return &S3Provider{client: client, bucket: cfg.Bucket}, nil
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
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		switch apiErr.ErrorCode() {
		case "NotFound", "NoSuchKey", "NoSuchBucket":
			return false, nil
		}
	}
	return false, err
}
