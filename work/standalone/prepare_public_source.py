"""Exclude private automation and tooltip probes from manager-importable builds."""

def prepare(source):
    driver = '-- Unattended development driver, enabled only by a local marker at startup.'
    start = source.index(driver)
    end = source.index('local function ui_diag(frames,tag)', start)
    source = source[:start] + source[end:]
    invocation = '        development_step(conf_data,frames)\n'
    assert source.count(invocation) == 1
    source = source.replace(invocation, '')
    probe = '    -- Private development probe: only localization is suppressed, preserving'
    start = source.index(probe)
    end = source.index('    -- the game keeps reading this buffer', start)
    source = source[:start] + source[end:]
    assert all(marker not in source for marker in (
        'development.enable', 'development.command', 'development.lua',
        'development_step(', 'test_tooltip_rows'))
    return source
