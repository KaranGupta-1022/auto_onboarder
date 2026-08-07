// Package api is a thin client for the Brain API's /ghost-note and
// /feedback endpoints. Field shapes mirror api/models.py exactly - see
// GhostNoteRequest/Response and FeedbackRequest/Response there.
package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type GhostNoteRequest struct {
	Query       string `json:"query"`
	TopResults  int    `json:"top_results"`
	GhostNoteID string `json:"ghost_note_id,omitempty"`
}

type GhostNoteResult struct {
	ChunkID        string                 `json:"chunk_id"`
	Text           string                 `json:"text"`
	RelevanceScore float64                `json:"relevance_score"`
	Metadata       map[string]interface{} `json:"metadata"`
}

type GhostNoteResponse struct {
	Query       string            `json:"query"`
	Results     []GhostNoteResult `json:"results"`
	Summary     string            `json:"summary,omitempty"`
	SummaryPath string            `json:"summary_path,omitempty"`
	Synthesized bool              `json:"synthesized,omitempty"`
}

type FeedbackRequest struct {
	ChunkID string `json:"chunk_id"`
	Query   string `json:"query"`
	Rating  string `json:"rating"` // "up" or "down"
}

type FeedbackResponse struct {
	Recorded  bool `json:"recorded"`
	TotalUp   int  `json:"total_up"`
	TotalDown int  `json:"total_down"`
}

type IntentRequest struct {
	Command string `json:"command"`
}

type IntentResponse struct {
	Label  string `json:"label"`  // "high_risk" | "low_risk" | "no_note"
	Source string `json:"source"` // "rules" | "model"
}

type errorResponse struct {
	Error      string `json:"error"`
	StatusCode int    `json:"status_code"`
}

type Client struct {
	baseURL string
	http    *http.Client
}

func New(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: timeout},
	}
}

func (c *Client) GhostNote(ctx context.Context, req GhostNoteRequest) (*GhostNoteResponse, error) {
	var resp GhostNoteResponse
	if err := c.post(ctx, "/ghost-note", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

func (c *Client) Feedback(ctx context.Context, req FeedbackRequest) (*FeedbackResponse, error) {
	var resp FeedbackResponse
	if err := c.post(ctx, "/feedback", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

func (c *Client) Intent(ctx context.Context, req IntentRequest) (*IntentResponse, error) {
	var resp IntentResponse
	if err := c.post(ctx, "/intent", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

func (c *Client) post(ctx context.Context, path string, body, out interface{}) error {
	payload, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("encode request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	httpResp, err := c.http.Do(httpReq)
	if err != nil {
		return fmt.Errorf("call %s: %w", path, err)
	}
	defer httpResp.Body.Close()

	respBody, err := io.ReadAll(httpResp.Body)
	if err != nil {
		return fmt.Errorf("read %s response: %w", path, err)
	}

	if httpResp.StatusCode != http.StatusOK {
		var apiErr errorResponse
		if json.Unmarshal(respBody, &apiErr) == nil && apiErr.Error != "" {
			return fmt.Errorf("%s: %s (status %d)", path, apiErr.Error, httpResp.StatusCode)
		}
		return fmt.Errorf("%s: unexpected status %d", path, httpResp.StatusCode)
	}

	if err := json.Unmarshal(respBody, out); err != nil {
		return fmt.Errorf("decode %s response: %w", path, err)
	}
	return nil
}
