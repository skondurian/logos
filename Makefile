# Logos binary compiler
# ──────────────────────────────────────────────────────────────────────────────
#
# Targets:
#   make                build build/logos_compile  (native C-emitter binary)
#   make install        install logoscc + runtime to PREFIX (default /usr/local)
#   make clean          remove build/
#   make test           run the full test suite
#   make verify         prove compile3==compile4 (self-hosting stability)
#
# Usage after build:
#   bin/logoscc examples/02_voting_rules.logos -o /tmp/voting
#   /tmp/voting
# ──────────────────────────────────────────────────────────────────────────────

CC      ?= cc
CFLAGS  ?= -O2 -lm
PREFIX  ?= /usr/local

RUNTIME_DIR = logos/runtime
RUNTIME_SRC = $(RUNTIME_DIR)/logos_runtime.c \
              $(RUNTIME_DIR)/logos_primitives.c \
              $(RUNTIME_DIR)/logos_meta.c \
              $(RUNTIME_DIR)/logos_lexer.c
RUNTIME_HDR = $(wildcard $(RUNTIME_DIR)/*.h)

LOGOS_SRC   = logos/compile-main.logos \
              logos/compiler.logos \
              logos/parser.logos \
              $(wildcard logos/stdlib/*.logos)

BUILD_DIR   = build

# macOS: increase default stack (8 MB → 256 MB) for deep CPS recursion
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS += -Wl,-stack_size,0x10000000
endif

# ── Primary target ────────────────────────────────────────────────────────────

.PHONY: all bootstrap verify clean install test

all: $(BUILD_DIR)/logos_compile

# ── Step 1: Python bootstrap → stable self-hosted C source ───────────────────
#
# The bootstrap uses the Python codegen to produce a first-gen binary, then
# self-compiles once to reach the stable fixed point (gen2 == gen3).
#
$(BUILD_DIR)/logos_compile.c: $(LOGOS_SRC) $(RUNTIME_SRC) $(RUNTIME_HDR)
	@mkdir -p $(BUILD_DIR)
	@echo "[1/3] Bootstrap: Python → $(BUILD_DIR)/logos_bootstrap.c"
	python3 -m logos compile logos/compile-main.logos \
	    --keep-c -o $(BUILD_DIR)/logos_bootstrap
	@echo "[2/3] Self-compile: bootstrap binary → stable C source"
	$(BUILD_DIR)/logos_bootstrap logos/compile-main.logos \
	    > $(BUILD_DIR)/logos_compile.c
	@echo "      Generated: $$(wc -l < $(BUILD_DIR)/logos_compile.c) lines"

# ── Step 2: Compile stable C source → native binary ──────────────────────────

$(BUILD_DIR)/logos_compile: $(BUILD_DIR)/logos_compile.c $(RUNTIME_SRC) $(RUNTIME_HDR)
	@echo "[3/3] Compile: C → native binary $(BUILD_DIR)/logos_compile"
	$(CC) $(BUILD_DIR)/logos_compile.c $(RUNTIME_SRC) \
	    -I$(RUNTIME_DIR) -o $@ $(CFLAGS) $(LDFLAGS)
	@echo "      OK: $@"

# ── Bootstrap only (skip self-compile) ───────────────────────────────────────

bootstrap:
	@mkdir -p $(BUILD_DIR)
	python3 -m logos compile logos/compile-main.logos \
	    --keep-c -o $(BUILD_DIR)/logos_bootstrap
	@echo "Bootstrap binary: $(BUILD_DIR)/logos_bootstrap"

# ── Verify self-hosting stability (gen3 == gen4) ─────────────────────────────

verify: $(BUILD_DIR)/logos_compile
	@echo "Verifying self-hosting stability..."
	$(BUILD_DIR)/logos_compile logos/compile-main.logos \
	    > $(BUILD_DIR)/logos_compile_check.c
	@diff $(BUILD_DIR)/logos_compile.c $(BUILD_DIR)/logos_compile_check.c \
	    && echo "PASS: compiler output is stable (fixed point)" \
	    || (echo "FAIL: gen3 != gen4" && exit 1)

# ── Install ───────────────────────────────────────────────────────────────────

INSTALL_BIN     = $(PREFIX)/bin
INSTALL_LIB     = $(PREFIX)/lib/logos
INSTALL_RUNTIME = $(INSTALL_LIB)/runtime

install: $(BUILD_DIR)/logos_compile
	@echo "Installing to $(PREFIX)..."
	install -d $(INSTALL_BIN) $(INSTALL_RUNTIME)
	install -m755 $(BUILD_DIR)/logos_compile $(INSTALL_LIB)/logos_compile
	install -m644 $(RUNTIME_SRC) $(RUNTIME_HDR) $(INSTALL_RUNTIME)/
	sed "s|__LOGOS_LIB__|$(INSTALL_LIB)|g" bin/logoscc \
	    > $(INSTALL_BIN)/logoscc
	chmod 755 $(INSTALL_BIN)/logoscc
	@echo "Installed: $(INSTALL_BIN)/logoscc"
	@echo "           $(INSTALL_LIB)/logos_compile"

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	python3 -m pytest tests/ -q

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	rm -rf $(BUILD_DIR)
