" Headless smoke test for colors/42vibes.vim.
"
" Run from the repository:
"   vim -Nu NONE -es -S test/smoke.vim
"   nvim --clean --headless -S test/smoke.vim
"
" The script loads the colorscheme for both backgrounds, asserts that every
" required group exists, that the documented groups are bold in gui and cterm,
" and that no error was raised while sourcing. Exit code 0 means success.

set nocompatible
let s:root = expand('<sfile>:p:h:h')
execute 'set runtimepath+=' . fnameescape(s:root)
set t_Co=256

let s:groups = [
      \ 'Normal', 'Comment', 'Constant', 'String', 'Character', 'Number',
      \ 'Boolean', 'Float', 'Identifier', 'Function', 'Statement',
      \ 'Conditional', 'Repeat', 'Label', 'Operator', 'Keyword', 'Exception',
      \ 'PreProc', 'Include', 'Define', 'Macro', 'PreCondit', 'Type',
      \ 'StorageClass', 'Structure', 'Typedef', 'Special', 'SpecialChar',
      \ 'Tag', 'Delimiter', 'SpecialComment', 'Debug', 'Underlined', 'Ignore',
      \ 'Error', 'Todo', 'ErrorMsg', 'WarningMsg', 'ModeMsg', 'MoreMsg',
      \ 'Question', 'Title', 'Directory', 'MatchParen', 'Cursor',
      \ 'CursorLine', 'CursorLineNr', 'LineNr', 'SignColumn', 'Visual',
      \ 'Search', 'IncSearch', 'StatusLine', 'StatusLineNC', 'VertSplit',
      \ 'Pmenu', 'PmenuSel', 'PmenuSbar', 'PmenuThumb', 'TabLine',
      \ 'TabLineSel', 'TabLineFill', 'DiffAdd', 'DiffChange', 'DiffDelete',
      \ 'DiffText', 'Folded', 'NonText', 'EndOfBuffer', 'SpellBad',
      \ 'SpellCap', 'SpellRare', 'SpellLocal', 'QuickFixLine', 'ColorColumn',
      \ 'WildMenu', 'markdownH1', 'markdownH2', 'markdownH3', 'markdownBold',
      \ 'markdownItalic', 'markdownCode', 'markdownLinkText',
      \ ]

if has('nvim')
  let s:groups += [
        \ '@comment', '@keyword', '@function', '@variable', '@string',
        \ '@number', '@type', '@operator', '@punctuation.delimiter',
        \ '@markup.heading.1', '@markup.heading.2', '@markup.heading.3',
        \ '@markup.strong',
        \ 'DiagnosticError', 'DiagnosticWarn', 'DiagnosticInfo',
        \ 'DiagnosticHint', 'DiagnosticOk',
        \ ]
endif

let s:bold = [
      \ 'Title', 'ErrorMsg', 'WarningMsg', 'Todo', 'StatusLine',
      \ 'markdownH1', 'markdownH2', 'markdownH3', 'markdownBold',
      \ ]

if has('nvim')
  let s:bold += ['@markup.heading.1', '@markup.heading.2', '@markup.heading.3']
endif

let s:errors = []
let s:log = []
let s:backgrounds = {}

function! s:has_attr(group, attr, mode) abort
  return synIDattr(hlID(a:group), a:attr, a:mode) ==# '1'
endfunction

function! s:hi_text(group) abort
  return substitute(execute('hi ' . a:group), "\n", ' ', 'g')
endfunction

function! s:check(mode) abort
  let v:errmsg = ''
  execute 'set background=' . a:mode
  try
    colorscheme 42vibes
  catch
    call add(s:errors, a:mode . ': colorscheme warf einen Fehler: ' . v:exception)
    return
  endtry
  if v:errmsg !=# ''
    call add(s:errors, a:mode . ': v:errmsg=' . v:errmsg)
  endif
  if get(g:, 'colors_name', '') !=# '42vibes'
    call add(s:errors, a:mode . ": g:colors_name='" . get(g:, 'colors_name', '') . "'")
  endif

  for group in s:groups
    if !hlexists(group)
      call add(s:errors, a:mode . ': Gruppe fehlt: ' . group)
    endif
  endfor

  for group in s:bold
    if synIDattr(hlID(group), 'bold', 'gui') !=# '1'
      call add(s:errors, a:mode . ': ' . group . ' ist nicht gui=bold')
    endif
    if synIDattr(hlID(group), 'bold', 'cterm') !=# '1'
      call add(s:errors, a:mode . ': ' . group . ' ist nicht cterm=bold')
    endif
  endfor

  " No group may inherit reverse or bold from the defaults that `hi clear`
  " and `syntax reset` install. Bold is allowed only for the whitelist above.
  for group in s:groups
    for mode in ['gui', 'cterm']
      if s:has_attr(group, 'reverse', mode)
        call add(s:errors, a:mode . ': ' . group . ' traegt unerwartet ' . mode . '=reverse')
      endif
      if s:has_attr(group, 'bold', mode) && index(s:bold, group) < 0
        call add(s:errors, a:mode . ': ' . group . ' traegt unerwartet ' . mode . '=bold')
      endif
    endfor
    " term attributes are not exposed through synIDattr(); inspect :hi.
    let hi = s:hi_text(group)
    if hi =~# 'term=[^ ]*reverse'
      call add(s:errors, a:mode . ': ' . group . ' traegt unerwartet term=reverse')
    endif
    if hi =~# 'term=[^ ]*bold' && index(s:bold, group) < 0
      call add(s:errors, a:mode . ': ' . group . ' traegt unerwartet term=bold')
    endif
  endfor

  " Regression checks for the four groups that used to inherit defaults.
  if s:hi_text('ModeMsg') =~# '\(term\|gui\|cterm\)=[^ ]*bold'
    call add(s:errors, a:mode . ': ModeMsg ist unerwartet fett')
  endif
  if s:hi_text('Identifier') =~# 'cterm=[^ ]*bold'
    call add(s:errors, a:mode . ': Identifier ist unerwartet cterm=bold')
  endif
  if s:hi_text('IncSearch') =~# '\(term\|gui\|cterm\)=[^ ]*reverse'
    call add(s:errors, a:mode . ': IncSearch ist unerwartet reverse')
  endif
  let s:spell_bg = matchstr(s:hi_text('SpellBad'), 'ctermbg=\zs\d\+')
  if s:spell_bg ==# '' || s:spell_bg ==# '12' || str2nr(s:spell_bg) < 16
    call add(s:errors, a:mode . ': SpellBad ctermbg=' . s:spell_bg
          \ . ' (erwartet definierter Palettenindex >= 16, nicht 12)')
  endif

  let fg = synIDattr(hlID('Normal'), 'fg', 'gui')
  let bg = synIDattr(hlID('Normal'), 'bg', 'gui')
  let cfg = synIDattr(hlID('Normal'), 'fg', 'cterm')
  let cbg = synIDattr(hlID('Normal'), 'bg', 'cterm')
  if fg ==# '' || bg ==# '' || cfg ==# '' || cbg ==# ''
    call add(s:errors, a:mode . ': Normal ohne gui/cterm Farben')
  endif
  let s:backgrounds[a:mode] = bg
  call add(s:log, printf('%s: Normal gui=%s/%s cterm=%s/%s, %d Gruppen',
        \ a:mode, fg, bg, cfg, cbg, len(s:groups)))
endfunction

syntax enable
call s:check('dark')
call s:check('light')

if get(s:backgrounds, 'dark', '') ==# get(s:backgrounds, 'light', '')
  call add(s:errors, 'dark und light haben denselben Normal-Hintergrund')
endif

" &background alone must reload the scheme (g:colors_name is set)
set background=dark
colorscheme 42vibes
let s:auto_dark = synIDattr(hlID('Normal'), 'bg', 'gui')
set background=light
let s:auto_light = synIDattr(hlID('Normal'), 'bg', 'gui')
if s:auto_light ==# s:auto_dark
  call add(s:errors, 'set background=light lädt das Colorscheme nicht neu')
endif
call add(s:log, printf('auto: dark=%s light=%s', s:auto_dark, s:auto_light))

call writefile(s:log, s:root . '/test/smoke.log')

if !empty(s:errors)
  call writefile(s:errors, s:root . '/test/smoke.log', 'a')
  cquit 1
endif

qall!
