<_mi_page_free_collect>:
   19270:	41 54                	push   %r12
   19272:	48 8d 57 40          	lea    0x40(%rdi),%rdx
   19276:	41 89 f4             	mov    %esi,%r12d
   19279:	55                   	push   %rbp
   1927a:	53                   	push   %rbx
   1927b:	48 8b 47 40          	mov    0x40(%rdi),%rax
   1927f:	48 89 fb             	mov    %rdi,%rbx
   19282:	48 89 c1             	mov    %rax,%rcx
   19285:	48 83 e1 fe          	and    $0xfffffffffffffffe,%rcx
   19289:	75 3d                	jne    192c8 <_mi_page_free_collect+0x58>
   1928b:	31 ed                	xor    %ebp,%ebp
   1928d:	48 8b 53 18          	mov    0x18(%rbx),%rdx
   19291:	48 85 d2             	test   %rdx,%rdx
   19294:	74 25                	je     192bb <_mi_page_free_collect+0x4b>
   19296:	48 8b 43 10          	mov    0x10(%rbx),%rax
   1929a:	48 85 c0             	test   %rax,%rax
   1929d:	0f 85 a5 00 00 00    	jne    19348 <_mi_page_free_collect+0xd8>
   192a3:	48 89 53 10          	mov    %rdx,0x10(%rbx)
   192a7:	48 c7 43 18 00 00 00 	movq   $0x0,0x18(%rbx)
   192ae:	00 
   192af:	c6 43 3f 00          	movb   $0x0,0x3f(%rbx)
   192b3:	48 89 df             	mov    %rbx,%rdi
   192b6:	e8 85 f2 ff ff       	callq  18540 <_mi_page_update_sample_countdown>
   192bb:	89 e8                	mov    %ebp,%eax
   192bd:	5b                   	pop    %rbx
   192be:	5d                   	pop    %rbp
   192bf:	41 5c                	pop    %r12
   192c1:	c3                   	retq   
   192c2:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
   192c8:	48 89 c6             	mov    %rax,%rsi
   192cb:	83 e6 01             	and    $0x1,%esi
   192ce:	f0 48 0f b1 32       	lock cmpxchg %rsi,(%rdx)
   192d3:	40 0f 94 c6          	sete   %sil
   192d7:	40 0f b6 f6          	movzbl %sil,%esi
   192db:	48 89 f7             	mov    %rsi,%rdi
   192de:	48 85 f6             	test   %rsi,%rsi
   192e1:	74 9f                	je     19282 <_mi_page_free_collect+0x12>
   192e3:	48 8b 01             	mov    (%rcx),%rax
   192e6:	48 89 ca             	mov    %rcx,%rdx
   192e9:	44 0f b7 4b 38       	movzwl 0x38(%rbx),%r9d
   192ee:	48 85 c0             	test   %rax,%rax
   192f1:	74 7d                	je     19370 <_mi_page_free_collect+0x100>
   192f3:	4d 85 c9             	test   %r9,%r9
   192f6:	74 7d                	je     19375 <_mi_page_free_collect+0x105>
   192f8:	4c 8b 00             	mov    (%rax),%r8
   192fb:	48 8d 7e 01          	lea    0x1(%rsi),%rdi
   192ff:	4d 85 c0             	test   %r8,%r8
   19302:	74 17                	je     1931b <_mi_page_free_collect+0xab>
   19304:	4c 89 c0             	mov    %r8,%rax
   19307:	49 39 f1             	cmp    %rsi,%r9
   1930a:	74 69                	je     19375 <_mi_page_free_collect+0x105>
   1930c:	4c 8b 00             	mov    (%rax),%r8
   1930f:	48 89 fe             	mov    %rdi,%rsi
   19312:	48 8d 7e 01          	lea    0x1(%rsi),%rdi
   19316:	4d 85 c0             	test   %r8,%r8
   19319:	75 e9                	jne    19304 <_mi_page_free_collect+0x94>
   1931b:	49 39 f9             	cmp    %rdi,%r9
   1931e:	72 55                	jb     19375 <_mi_page_free_collect+0x105>
   19320:	0f b7 73 28          	movzwl 0x28(%rbx),%esi
   19324:	48 39 fe             	cmp    %rdi,%rsi
   19327:	72 69                	jb     19392 <_mi_page_free_collect+0x122>
   19329:	48 8b 73 18          	mov    0x18(%rbx),%rsi
   1932d:	bd 01 00 00 00       	mov    $0x1,%ebp
   19332:	48 89 30             	mov    %rsi,(%rax)
   19335:	48 89 4b 18          	mov    %rcx,0x18(%rbx)
   19339:	48 29 7b 28          	sub    %rdi,0x28(%rbx)
   1933d:	e9 54 ff ff ff       	jmpq   19296 <_mi_page_free_collect+0x26>
   19342:	66 0f 1f 44 00 00    	nopw   0x0(%rax,%rax,1)
   19348:	45 84 e4             	test   %r12b,%r12b
   1934b:	0f 84 62 ff ff ff    	je     192b3 <_mi_page_free_collect+0x43>
   19351:	48 8b 0a             	mov    (%rdx),%rcx
   19354:	48 89 d6             	mov    %rdx,%rsi
   19357:	48 85 c9             	test   %rcx,%rcx
   1935a:	74 0b                	je     19367 <_mi_page_free_collect+0xf7>
   1935c:	48 89 ce             	mov    %rcx,%rsi
   1935f:	48 8b 09             	mov    (%rcx),%rcx
   19362:	48 85 c9             	test   %rcx,%rcx
   19365:	75 f5                	jne    1935c <_mi_page_free_collect+0xec>
   19367:	48 89 06             	mov    %rax,(%rsi)
   1936a:	e9 34 ff ff ff       	jmpq   192a3 <_mi_page_free_collect+0x33>
   1936f:	90                   	nop
   19370:	48 89 c8             	mov    %rcx,%rax
   19373:	eb a6                	jmp    1931b <_mi_page_free_collect+0xab>
   19375:	48 8d 35 b4 31 01 00 	lea    0x131b4(%rip),%rsi        # 2c530 <mi_os_mem_config_default+0xcb0>
   1937c:	bf 0e 00 00 00       	mov    $0xe,%edi
   19381:	31 c0                	xor    %eax,%eax
   19383:	bd 01 00 00 00       	mov    $0x1,%ebp
   19388:	e8 83 62 ff ff       	callq  f610 <_mi_error_message>
   1938d:	e9 fb fe ff ff       	jmpq   1928d <_mi_page_free_collect+0x1d>
   19392:	48 8d 35 e7 31 01 00 	lea    0x131e7(%rip),%rsi        # 2c580 <mi_os_mem_config_default+0xd00>
   19399:	bf 0e 00 00 00       	mov    $0xe,%edi
   1939e:	31 c0                	xor    %eax,%eax
   193a0:	bd 01 00 00 00       	mov    $0x1,%ebp
   193a5:	e8 66 62 ff ff       	callq  f610 <_mi_error_message>
   193aa:	e9 de fe ff ff       	jmpq   1928d <_mi_page_free_collect+0x1d>
   193af:	90                   	nop
