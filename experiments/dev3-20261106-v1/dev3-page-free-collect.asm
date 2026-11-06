<_mi_page_free_collect>:
   18790:	41 54                	push   %r12
   18792:	41 89 f4             	mov    %esi,%r12d
   18795:	55                   	push   %rbp
   18796:	53                   	push   %rbx
   18797:	48 8b 47 40          	mov    0x40(%rdi),%rax
   1879b:	48 89 fb             	mov    %rdi,%rbx
   1879e:	48 a9 fe ff ff ff    	test   $0xfffffffffffffffe,%rax
   187a4:	75 3a                	jne    187e0 <_mi_page_free_collect+0x50>
   187a6:	31 ed                	xor    %ebp,%ebp
   187a8:	48 8b 43 18          	mov    0x18(%rbx),%rax
   187ac:	48 85 c0             	test   %rax,%rax
   187af:	74 23                	je     187d4 <_mi_page_free_collect+0x44>
   187b1:	48 83 7b 10 00       	cmpq   $0x0,0x10(%rbx)
   187b6:	75 58                	jne    18810 <_mi_page_free_collect+0x80>
   187b8:	48 89 43 10          	mov    %rax,0x10(%rbx)
   187bc:	48 c7 43 18 00 00 00 	movq   $0x0,0x18(%rbx)
   187c3:	00 
   187c4:	48 8b 43 08          	mov    0x8(%rbx),%rax
   187c8:	c6 43 3f 00          	movb   $0x0,0x3f(%rbx)
   187cc:	48 89 df             	mov    %rbx,%rdi
   187cf:	e8 3c fa ff ff       	callq  18210 <_mi_page_update_sample_countdown>
   187d4:	89 e8                	mov    %ebp,%eax
   187d6:	5b                   	pop    %rbx
   187d7:	5d                   	pop    %rbp
   187d8:	41 5c                	pop    %r12
   187da:	c3                   	retq   
   187db:	0f 1f 44 00 00       	nopl   0x0(%rax,%rax,1)
   187e0:	48 8b 47 40          	mov    0x40(%rdi),%rax
   187e4:	48 8d 57 40          	lea    0x40(%rdi),%rdx
   187e8:	48 89 c1             	mov    %rax,%rcx
   187eb:	48 89 c6             	mov    %rax,%rsi
   187ee:	83 e1 01             	and    $0x1,%ecx
   187f1:	f0 48 0f b1 0a       	lock cmpxchg %rcx,(%rdx)
   187f6:	75 f0                	jne    187e8 <_mi_page_free_collect+0x58>
   187f8:	48 83 e6 fe          	and    $0xfffffffffffffffe,%rsi
   187fc:	74 a8                	je     187a6 <_mi_page_free_collect+0x16>
   187fe:	48 89 df             	mov    %rbx,%rdi
   18801:	bd 01 00 00 00       	mov    $0x1,%ebp
   18806:	e8 25 85 ff ff       	callq  10d30 <mi_page_thread_collect_to_local>
   1880b:	eb 9b                	jmp    187a8 <_mi_page_free_collect+0x18>
   1880d:	0f 1f 00             	nopl   (%rax)
   18810:	48 89 c6             	mov    %rax,%rsi
   18813:	b9 01 00 00 00       	mov    $0x1,%ecx
   18818:	45 84 e4             	test   %r12b,%r12b
   1881b:	74 af                	je     187cc <_mi_page_free_collect+0x3c>
   1881d:	0f 1f 00             	nopl   (%rax)
   18820:	48 8b 16             	mov    (%rsi),%rdx
   18823:	48 85 d2             	test   %rdx,%rdx
   18826:	74 28                	je     18850 <_mi_page_free_collect+0xc0>
   18828:	48 89 d6             	mov    %rdx,%rsi
   1882b:	0f b7 53 38          	movzwl 0x38(%rbx),%edx
   1882f:	48 83 c1 01          	add    $0x1,%rcx
   18833:	48 39 ca             	cmp    %rcx,%rdx
   18836:	73 e8                	jae    18820 <_mi_page_free_collect+0x90>
   18838:	48 8d 35 91 5c 01 00 	lea    0x15c91(%rip),%rsi        # 2e4d0 <mi_os_mem_config_default+0xd50>
   1883f:	bf 0e 00 00 00       	mov    $0xe,%edi
   18844:	31 c0                	xor    %eax,%eax
   18846:	e8 e5 7e ff ff       	callq  10730 <_mi_error_message>
   1884b:	eb 87                	jmp    187d4 <_mi_page_free_collect+0x44>
   1884d:	0f 1f 00             	nopl   (%rax)
   18850:	48 8b 53 10          	mov    0x10(%rbx),%rdx
   18854:	48 89 16             	mov    %rdx,(%rsi)
   18857:	48 89 43 10          	mov    %rax,0x10(%rbx)
   1885b:	48 c7 43 18 00 00 00 	movq   $0x0,0x18(%rbx)
   18862:	00 
   18863:	c6 43 3f 00          	movb   $0x0,0x3f(%rbx)
   18867:	e9 60 ff ff ff       	jmpq   187cc <_mi_page_free_collect+0x3c>
   1886c:	0f 1f 40 00          	nopl   0x0(%rax)
