package main

// Real-engine pre/post-inference control for Data Point 2.
//
// The engine (NOL8/Themis :443 or RE2/Aergia :444) only does literal replacement,
// so the boundary policy (demos/policies/boundary.nol) maps every governed literal
// to a short sentinel. This mode calls the engine at BOTH control points - once on
// the prompt (govern what reaches the model) and once on the model output (govern
// what leaves it) - and derives the block/mask/route/tag action from which sentinel
// the engine emitted. Same policy runs on both engines, exactly like Data Point 1,
// so themis_api_infer vs aergia_api_infer is a like-for-like comparison.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// EngineConfig points at one real engine's data plane.
type EngineConfig struct {
	Endpoint  string
	Token     string
	Timeout   time.Duration
	ModeLabel string
}

func loadEngineConfig(modeLabel, endpointEnv, tokenEnv string) (EngineConfig, error) {
	endpoint := strings.TrimSpace(os.Getenv(endpointEnv))
	if endpoint == "" {
		return EngineConfig{}, fmt.Errorf("%s is required for %s mode", endpointEnv, modeLabel)
	}
	timeout := 30 * time.Second
	if raw := strings.TrimSpace(os.Getenv("ENGINE_TIMEOUT_MS")); raw != "" {
		var ms int
		if _, err := fmt.Sscanf(raw, "%d", &ms); err == nil && ms > 0 {
			timeout = time.Duration(ms) * time.Millisecond
		}
	}
	return EngineConfig{
		Endpoint:  endpoint,
		Token:     strings.TrimSpace(os.Getenv(tokenEnv)),
		Timeout:   timeout,
		ModeLabel: modeLabel,
	}, nil
}

// callEngineProcess sends one string through the engine's literal redaction and
// returns the processed text (policy sentinels substituted in place).
func callEngineProcess(client *http.Client, cfg EngineConfig, text string) (string, error) {
	payload, err := json.Marshal(map[string]string{"message": text})
	if err != nil {
		return "", err
	}
	req, err := http.NewRequest(http.MethodPost, cfg.Endpoint, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("engine returned status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var parsed struct {
		Result struct {
			Message string `json:"message"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "", fmt.Errorf("decode engine response: %w", err)
	}
	return parsed.Result.Message, nil
}

// Sentinels emitted by demos/policies/boundary.nol.
const (
	sentBlock    = "[BLOCK]"
	sentRoute    = "[ROUTE]"
	sentMaskCard = "[MASK_CARD]"
	sentMaskAcct = "[MASK_ACCT]"
	sentTagInt   = "[TAG_INT]"
	sentBlockOut = "[BLOCK_OUT]"
	sentTagPriv  = "[TAG_PRIV]"
)

func hasMaskSentinel(s string) bool {
	return strings.Contains(s, sentMaskCard) || strings.Contains(s, sentMaskAcct)
}

// derivePreAction maps the engine's processed prompt to a pre-inference action.
// block/route win (the prompt never reaches the model); otherwise mask (a value
// was redacted) outranks tag (an internal project was flagged).
func derivePreAction(processed string) (string, []string) {
	switch {
	case strings.Contains(processed, sentBlock):
		return "block", []string{}
	case strings.Contains(processed, sentRoute):
		return "route", []string{}
	}
	action := "allow"
	tags := []string{}
	if hasMaskSentinel(processed) {
		action = "mask"
	}
	if strings.Contains(processed, sentTagInt) {
		tags = append(tags, "internal_only")
		if action == "allow" {
			action = "tag"
		}
	}
	return action, tags
}

// derivePostAction maps the engine's processed model output to a post action.
func derivePostAction(processed string) (string, string, []string) {
	if strings.Contains(processed, sentBlockOut) {
		return "block", "[BLOCKED_OUTPUT]", []string{}
	}
	action := "allow"
	tags := []string{}
	if hasMaskSentinel(processed) {
		action = "mask"
	}
	if strings.Contains(processed, sentTagPriv) {
		tags = append(tags, "privileged_context")
		if action == "allow" {
			action = "tag"
		}
	}
	return action, processed, tags
}

func runEngineInfer(prompts []PromptRecord, outputDir string, cfg EngineConfig) (SummaryStats, error) {
	start := time.Now()
	stats := SummaryStats{Mode: cfg.ModeLabel}
	var records []OutputRecord
	client := &http.Client{Timeout: cfg.Timeout}

	for _, prompt := range prompts {
		stats.PromptsTotal++
		stats.PromptTokensInEst += tokenEstimate(prompt.PromptText)

		// Pre-inference control: govern what may reach the model.
		preStart := time.Now()
		preProcessed, err := callEngineProcess(client, cfg, prompt.PromptText)
		if err != nil {
			return stats, fmt.Errorf("prompt %s pre-inference: %w", prompt.PromptID, err)
		}
		stats.PreprocessMs += float64(time.Since(preStart).Microseconds()) / 1000.0
		preAction, preTags := derivePreAction(preProcessed)

		// allow/mask/tag forward the (possibly redacted) processed prompt;
		// block/route stop it before the model.
		promptProcessed := preProcessed
		if preAction == "block" || preAction == "route" {
			promptProcessed = prompt.PromptText
		}

		switch preAction {
		case "allow":
			stats.PromptsAllowed++
		case "mask":
			stats.PromptsMasked++
		case "block":
			stats.PromptsBlocked++
			stats.InferenceCallsAvoided++
		case "route":
			stats.PromptsRouted++
			stats.InferenceCallsAvoided++
		case "tag":
			stats.PromptsTagged++
		}

		inferenceCalled := preAction != "block" && preAction != "route"
		rawOutput := ""
		postAction := "allow"
		postTags := []string{}
		finalOutput := ""

		if inferenceCalled {
			stats.InferenceCallsMade++
			stats.PromptTokensForwardedEst += tokenEstimate(promptProcessed)

			stub := modelStub(prompt, promptProcessed)
			rawOutput = stub.RawModelOutput
			stats.OutputsTotal++
			stats.OutputTokensRawEst += tokenEstimate(rawOutput)

			// Post-inference control: govern what may leave the model.
			postStart := time.Now()
			postProcessed, err := callEngineProcess(client, cfg, rawOutput)
			if err != nil {
				return stats, fmt.Errorf("prompt %s post-inference: %w", prompt.PromptID, err)
			}
			stats.PostprocessMs += float64(time.Since(postStart).Microseconds()) / 1000.0
			postAction, finalOutput, postTags = derivePostAction(postProcessed)

			switch postAction {
			case "allow":
				stats.OutputsAllowed++
			case "mask":
				stats.OutputsMasked++
			case "block":
				stats.OutputsBlocked++
			case "tag":
				stats.OutputsTagged++
			}
			stats.OutputTokensReleasedEst += tokenEstimate(finalOutput)
		}

		records = append(records, OutputRecord{
			PromptID:        prompt.PromptID,
			Mode:            cfg.ModeLabel,
			Category:        prompt.Category,
			PreAction:       preAction,
			PreTags:         dedupeTags(preTags),
			PromptOriginal:  prompt.PromptText,
			PromptProcessed: promptProcessed,
			InferenceCalled: inferenceCalled,
			RawModelOutput:  rawOutput,
			PostAction:      postAction,
			PostTags:        dedupeTags(postTags),
			FinalOutput:     finalOutput,
		})
	}

	totalElapsedMs := float64(time.Since(start).Milliseconds())
	if totalElapsedMs <= 0 {
		totalElapsedMs = 1
	}
	stats.TotalControlMs = stats.PreprocessMs + stats.PostprocessMs
	stats.RecordsPerSec = float64(stats.PromptsTotal) / (totalElapsedMs / 1000.0)

	if err := writeOutputJSONL(filepath.Join(outputDir, cfg.ModeLabel+"_output.jsonl"), records); err != nil {
		return stats, err
	}
	return stats, writeSummaryCSV(filepath.Join(outputDir, "run_01.csv"), stats)
}
