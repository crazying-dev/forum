// Package sse 提供进程内 SSE 广播 Hub（单 poller 产生事件，按 topic 扇出）。
package sse

import "sync"

// Event SSE 事件。
type Event struct {
	ID   string
	Type string
	Data any
}

// Client 一个 SSE 订阅者。
type Client struct {
	Ch   chan Event
	once sync.Once
	done chan struct{}
}

func newClient(buffer int) *Client {
	if buffer <= 0 {
		buffer = 128
	}
	return &Client{Ch: make(chan Event, buffer), done: make(chan struct{})}
}

// Close 关闭订阅者（幂等）。
func (c *Client) Close() {
	c.once.Do(func() { close(c.done) })
}

// Done 返回关闭信号。
func (c *Client) Done() <-chan struct{} { return c.done }

// Hub topic 广播中心。
type Hub struct {
	mu     sync.RWMutex
	topics map[string]map[*Client]struct{}
}

// NewHub 创建 Hub。
func NewHub() *Hub {
	return &Hub{topics: map[string]map[*Client]struct{}{}}
}

// Subscribe 订阅 topic；buffer 默认 128。
func (h *Hub) Subscribe(topic string, buffer int) *Client {
	c := newClient(buffer)
	h.mu.Lock()
	if h.topics[topic] == nil {
		h.topics[topic] = map[*Client]struct{}{}
	}
	h.topics[topic][c] = struct{}{}
	h.mu.Unlock()
	return c
}

// Unsubscribe 取消订阅。
func (h *Hub) Unsubscribe(topic string, c *Client) {
	if c == nil {
		return
	}
	h.mu.Lock()
	if set := h.topics[topic]; set != nil {
		delete(set, c)
		if len(set) == 0 {
			delete(h.topics, topic)
		}
	}
	h.mu.Unlock()
	c.Close()
}

// Broadcast 非阻塞广播；慢客户端丢弃事件（由 handler 的写超时/心跳负责断开）。
func (h *Hub) Broadcast(topic string, ev Event) {
	h.mu.RLock()
	set := h.topics[topic]
	clients := make([]*Client, 0, len(set))
	for c := range set {
		clients = append(clients, c)
	}
	h.mu.RUnlock()
	for _, c := range clients {
		select {
		case c.Ch <- ev:
		case <-c.Done():
		default:
			// 队列满：丢弃该事件，避免阻塞 poller
		}
	}
}

// Count 返回 topic 当前订阅数（监控用）。
func (h *Hub) Count(topic string) int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.topics[topic])
}
