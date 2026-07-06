# TypeScript & Next.js 速成指南

> **读者定位**：有 Python + Java + Vue 背景的开发者，快速上手 TypeScript 和 Next.js
> **项目背景**：工作知识库桌面客户端（Tauri + Next.js），PRD v2.9
> **日期**：2026-06-26

---

## 目录

- [第一部分：TypeScript 基础](#第一部分typescript-基础)
  - [1.1 静态类型 ≠ 必须手写类型](#11-静态类型--必须手写类型)
  - [1.2 基础类型对照](#12-基础类型对照)
  - [1.3 可选属性 ? ：属性可以不存在](#13-可选属性--属性可以不存在)
  - [1.4 const vs let vs type vs interface vs class](#14-const-vs-let-vs-type-vs-interface-vs-class)
  - [1.5 interface：给数据画一张身份证](#15-interface给数据画一张身份证)
  - [1.6 函数类型](#16-函数类型)
  - [1.7 解构赋值](#17-解构赋值)
  - [1.8 箭头函数 vs 普通函数](#18-箭头函数-vs-普通函数)
  - [1.9 类型断言 as](#19-类型断言-as)
  - [1.10 联合类型 |](#110-联合类型-)
  - [1.11 ?? 空值合并运算符](#11--空值合并运算符)
  - [1.12 类型推断的边界](#112-类型推断的边界)
  - [1.13 Python 的 TypedDict / dataclass / 纯 class — 和 TS interface 的关系](#113-python-的-typeddict--dataclass--纯-class--和-ts-interface-的关系)
  - [1.14 TypeScript 的类型检查是真检查还是第三方工具](#114-typescript-的类型检查是真检查还是第三方工具)
- [第二部分：框架基础](#第二部分框架基础)
  - [2.1 JSX / TSX 是什么](#21-jsx--tsx-是什么)
  - [2.2 React vs Next.js](#22-react-vs-nextjs)
  - [2.3 Server Component vs Client Component](#23-server-component-vs-client-component)
  - [2.4 Next.js API Routes](#24-nextjs-api-routes)
  - [2.5 SEO 是什么](#25-seo-是什么)
  - [2.6 Express 是什么](#26-express-是什么)
  - [2.7 Tree-shaking 与 import type](#27-tree-shaking-与-import-type)
  - [2.8 ES6 模块系统](#28-es6-模块系统)
- [第三部分：项目高频代码模式](#第三部分项目高频代码模式)
- [第四部分：学习路线与资源](#第四部分学习路线与资源)

---

# 第一部分：TypeScript 基础

## 1.1 静态类型 ≠ 必须手写类型

**核心认知**：TypeScript = JavaScript + 类型注解。所有 JS 代码都是合法 TS 代码。静态类型说的是"编译时检查"，不是"必须手写类型声明"。

```
Java 风格的静态类型：你写类型，编译器检查（手写为主）
TypeScript 风格的静态类型：编译器帮你推断类型，只在推断不了时才需要你写（推断为主）
Python 是动态类型：完全没有编译期检查，类型错误只有运行时才知道
```

三种语言的对比：

```java
// Java：必须手写类型，编译器检查
int add(int a, int b) {
    return a + b;
}
add("hello", 123);   // ❌ 编译报错！
```

```python
# Python：不写类型，运行时才报错
def add(a, b):
    return a + b
add("hello", 123)    # ✅ 不报错，运行时可能 TypeError
```

```typescript
// TypeScript：推断为主，参数必须写，返回值可省
function add(a: number, b: number) {    // 参数必须写
    return a + b                         // 返回值推断为 number，不需要手写
}
add("hello", 123)   // ❌ 编译报错！和 Java 一样
```

类型推断的原理——编译器从右往左读值：

```typescript
const name = "张三"      // 看到 "张三" 是 string → 推断 name 为 string
const age = 25           // 看到 25 是 number → 推断 age 为 number
const items = [1, 2, 3]  // 推断为 number[]
const doc = {
    title: "测试",
    type: "source",     // 推断为 string（不是 "source" 字面量）
    tags: ["支付"],
}
```

推断不了的四种场景——必须手写：

```typescript
// ① 函数参数（编译器无法知道调用者会传什么）
function greet(name: string) { }    // 必须写
function greet(name) { }            // name 推断为 any（不好）

// ② 空对象 / 空数组
const config = {}              // 推断为 {}（啥属性都不能加）
const config: SearchConfig = { mode: "hybrid", topK: 5 }   // 必须写
const items: string[] = []     // 必须写，否则推断为 never[]

// ③ any 传播（一个 any 污染整条链）
function process(data: any) {
    const name = data.name          // any
    const upper = name.toUpperCase() // any —— 没有类型检查了
}

// ④ 需要比推断更精确的类型
const doc = { title: "测试", type: "source", tags: [] }
// type 推断为 string，但我想限制只能是 "source"|"entity"|...
const doc: WikiDocument = { title: "测试", type: "source", tags: [] }
```

---

## 1.2 基础类型对照

```
Python          →  TypeScript
str             →  string
int / float     →  number（不区分整数和浮点）
bool            →  boolean
None            →  null | undefined
list[str]       →  string[]
dict            →  Record<string, any> 或 { key: type }
tuple           →  [string, number]
Any             →  any（逃逸类型检查，慎用）
```

常用类型速查：

```typescript
// 数组
const names: string[] = ["张三", "李四"]
const nums: number[] = [1, 2, 3]

// 只读数组
const names: readonly string[] = ["张三", "李四"]
// names.push("王五")   // ❌ 不能修改

// 任意对象
const data: Record<string, unknown> = { name: "张三", age: 25 }

// 可选属性
type User = { name: string; email?: string }

// 联合类型
type Status = "active" | "inactive" | "pending"
type Result = string | Error

// 空值安全
const x = obj?.prop         // obj 为 null/undefined → undefined
const y = obj?.prop ?? "默认"  // obj.prop 为 null/undefined → "默认"
```

---

## 1.3 可选属性 ? ：属性可以不存在

`?` 不是"默认值是 null"。它的本质是：**这个属性可以从对象中完全不存在**。

```typescript
interface User {
    name: string           // 必须有，没有就报错
    email?: string         // 可以有，也可以没有
}

const u1: User = { name: "张三" }                     // ✅ email 不存在
const u2: User = { name: "李四", email: "li@test" }   // ✅ email 存在
const u3: User = { name: "王五", email: 123 }         // ❌ 类型错误
```

访问时的类型：

```typescript
console.log(u1.email)    // undefined（不是 null！JS 中 undefined 和 null 是两个不同的值）
console.log(u2.email)    // "li@test"

// u1.email 的类型是 string | undefined
u1.email.toUpperCase()     // ❌ 报错！undefined 上没有 toUpperCase
u1.email?.toUpperCase()    // ✅ 可选链：如果是 undefined 就跳过
if (u1.email) {
    u1.email.toUpperCase()  // ✅ 这里面编译器知道 email 一定有值
}
```

和 Python/Java 的区别：

```python
# Python：属性始终存在，只是值可能是 None
class User:
    def __init__(self, name: str, email: str | None = None):
        self.name = name
        self.email = email    # 属性永远存在，值可能是 None

u1 = User("张三")
print(u1.email)     # None（属性存在，值是 None）
print(hasattr(u1, "email"))  # True（属性永远在）
```

```java
// Java：没有可选属性概念，用重载实现
class User {
    private String name;
    private String email;
    public User(String name) { this(name, null); }
    public User(String name, String email) { this.name = name; this.email = email; }
}
```

**TS 的 `?` 让属性可以不存在（不是存在但值为 null），和 Python/Java 都不同。**

三个"可选"操作符的区别：

```typescript
// ① ?. — 可选链（Optional Chaining）
config.timeout?.toString()          // undefined（不会报错）
config.timeout?.toFixed(2)           // undefined
// 等价于 if (config.timeout !== null && config.timeout !== undefined) { ... }

// ② ?? — 空值合并（Nullish Coalescing）
const t1 = config.timeout ?? 3000     // timeout 是 undefined → 返回 3000
const t2 = config.timeout ?? 0        // timeout 是 undefined → 返回 0
// 如果 config.timeout = 0：
const t3 = config.timeout ?? 3000     // → 0（0 不是 null/undefined！）
const t4 = config.timeout || 3000     // → 3000（0 是 falsy！这里 || 和 ?? 差异）

// ③ ! — 非空断言（Non-null Assertion）——慎用！
config.timeout!.toFixed(2)
// 告诉编译器"我保证它不是 null/undefined，别检查了"
// 运行时如果真的是 undefined → 爆炸
```

项目中大量使用：

```typescript
interface Chunk {
    id: string
    content: string
    tokenCount: number
    embedding?: number[]        // 刚分块完还没嵌入时，没有向量
    salience?: number            // Phase 5 才启用
    effectiveDate?: string       // 多数文档没有明确生效日
}

// 使用：
const vec = chunk.embedding ?? []   // 没有就返回空数组
if (chunk.embedding) {
    chunk.embedding.map(v => v * 2)   // 这里确定有值
}
```

---

## 1.4 const vs let vs type vs interface vs class

这四个东西**完全不在同一个维度**：

```
创建值（运行时存在于内存中）：
    const / let     → 创建变量
    class           → 创建类（可以 new）

创建类型（编译后消失，不占内存）：
    type            → 类型别名
    interface       → 对象形状描述
```

### const vs let vs var

```typescript
// const — 不可重新赋值（推荐默认使用）
const name = "张三"
name = "李四"        // ❌ Cannot assign to 'name' because it is a constant

// ⚠️ const 对对象/数组只锁引用，不锁内容！
const user = { name: "张三", age: 25 }
user.name = "李四"     // ✅ 可以改属性！（对象引用没变）
user = { name: "王五" } // ❌ 不能重新赋值整个对象

const items = [1, 2, 3]
items.push(4)          // ✅ 可以修改数组内容
items = [5, 6, 7]      // ❌ 不能重新赋值

// let — 可以重新赋值
let count = 0
count = 1              // ✅
count = "hello"        // ❌ 类型推断为 number 后不能变成 string

// var — 旧语法，有作用域 bug，永远不要用
if (true) {
    var x = 1
}
console.log(x)         // ✅ 1（泄漏到 if 外面了！let 是块级作用域）
```

和 Java/Python 的对比：

```
TypeScript        Java                  Python
────────────────────────────────────────────────
const x = 5       final int x = 5      x = 5（无保护，全大写命名约定）
                  static final x = 5  和 const 无关！static 是类级别
let x = 5         int x = 5            x = 5（无保护）
```

```
const ≈ Java 的 final（赋值后不能改引用）
const ≈ Python 没有等价物（Python 全大写命名约定 MAX_SIZE = 100，但无强制力）
const ≠ Java 的 static final（static 管的是"属于类还是实例"，和能不能改无关）
```

什么时候用 const vs let：

```typescript
// 默认 const
const API_URL = "http://localhost:8000"
const MAX_CHUNK_TOKENS = 300

// 需要 let：计数器、状态累积、条件赋值
let count = 0
for (let i = 0; i < 10; i++) { count += 1 }

let results: SearchResult[] = []
for (const batch of batches) {
    results = [...results, ...newResults]     // results 在改 → let
}

// 不需要 let 的情况：用三元/?? 即可
const mode = params.get("mode") ?? "hybrid"    // 不需要 let

// 数组 push：const 就够了
const items: string[] = []
items.push("hello")    // ✅ const 数组可以 push（引用没变，内容变了）
```

### type

`type` 定义类型别名，编译后完全消失，不创建任何变量：

```typescript
type DocType = "source" | "entity" | "concept" | "synthesis"  // 联合类型别名
type ID = string                                  // 简单别名
type SearchResult = {                              // 对象形状
    title: string
    score: number
}
type Callback = (data: string) => void           // 函数类型
type Pair<T> = [T, T]                             // 泛型
```

### interface

`interface` 描述对象的形状，编译后也完全消失（详见 1.5 节）。

`type` 和 `interface` 的选择：
- 描述对象结构 → 用 `interface`
- 定义联合类型/函数类型/工具类型 → 用 `type`
- 不确定 → 用 `interface`（项目里 90% 场景）

`interface` 有两个 `type` 没有的能力：
1. 声明合并（同名 interface 自动合并——扩展第三方库类型时有用）
2. implements 检查（class implements interface）

### class

TS 完全支持 class，语法和 Java 几乎一模一样。但前端开发中 **90% 用 interface，很少用 class**。

```typescript
// class：有行为、有状态、能实例化（运行时存在）
class Chunker {
    private maxTokens: number

    constructor(maxTokens: number = 300) {
        this.maxTokens = maxTokens
    }

    split(text: string): string[] {
        return text.split(/[。！？]/)
    }

    private countCJK(text: string): number {
        return [...text].filter(c => /[\u4e00-\u9fff]/.test(c)).length
    }
}

const chunker = new Chunker(300)
const chunks = chunker.split("长文本...")
```

什么时候用 class vs interface：
- **class**：有行为逻辑（方法、私有状态）、需要 new、需要继承
- **interface**：纯数据描述、只是数据的容器（API 返回的 JSON）

前端数据从 API 获取（JSON），不需要 class 的方法/构造函数，只需 interface 描述结构。

---

## 1.5 interface：给数据画一张身份证

### 为什么需要 interface

没有 interface 时的问题——`any` 传播：

```typescript
async function loadDocuments() {
    const data = await fetch("/api/documents").then(r => r.json())
    // data 类型是 any

    const title = data[0].titlee       // 拼写错误！多了个 e
    // ✅ 编译器不报错（any 上存在任何属性都不报错）
    // 运行时：undefined，排查半小时
}
```

有 interface 后：

```typescript
interface WikiDocument {
    title: string
    type: "source" | "entity" | "concept" | "synthesis"
    tags: string[]
}

async function loadDocuments() {
    const data: WikiDocument[] = await fetch("/api/documents").then(r => r.json())

    const title = data[0].titlee
    // ❌ 编译报错！WikiDocument 上不存在 titlee
    // Property 'titlee' does not exist on type 'WikiDocument'
    // 1 秒发现拼写错误，不需要运行时排查
}
```

### interface 解决的三个核心问题

1. **编译期类型检查**——写代码时发现错误（拼写、类型不匹配）
2. **IDE 智能提示**——敲 `doc.` 弹出所有属性，不需要记忆
3. **代码自文档化**——函数签名一眼看出返回什么数据

### 和 Java interface 的区别

```
Java interface 属性                    TS interface 属性
─────────────────────────────────────────────────────────
int MAX_SIZE = 100;              title: string

是值（100 这个数字真实存在）       不是值（string 只是个类型标记）
运行时存在                          运行时消失
public static final（类级别常量）    描述实例的结构
所有实现类共享同一个值              每个实例有自己的值
不能改（final）                     可以改（实例属性）
只能是常量                          可以是任何属性
```

```java
// Java：interface 里放常量 + 方法定义
public interface Config {
    int MAX_SIZE = 100;    // public static final，运行时存在，所有类共享
}

// TS：interface 只描述结构，不定义值
interface WikiDocument {
    title: string          // 每个实例各自的属性，不是常量
    tags: string[]
}

// TS 中类似 Java interface 常量的东西 → 用 const
const MAX_SIZE = 100
const CONFIG = {
    MAX_SIZE: 100,
    DEFAULT_MODE: "hybrid" as const,
} as const
```

```
Java interface ≈ 常量声明 + 行为契约（方法签名）→ 类 implements → new 实例
TS interface ≈ 对象形状描述（数据结构）→ 直接赋值对象 → 用属性

Java interface 的"常量"功能 → TS 用 const / 对象常量代替
Java interface 的"行为契约"功能 → TS interface 也能描述方法签名（但前端很少用）
TS interface 的"数据形状"功能 → Java 没有直接对应（Java 用 class 或 Record）
```

---

## 1.6 函数类型

### 返回类型

```typescript
// 推断能覆盖时，不写也没问题
function double(x: number) {
    return x * 2          // 推断返回 number
}

// 复杂返回类型，推荐写（自文档化）
function search(query: string): SearchResult[] {
    return db.search(query)
}

// 返回多种类型（联合类型）
function parse(input: string): WikiDocument | null {
    try { return JSON.parse(input) } catch { return null }
}

// 返回 Promise（异步）
async function search(query: string): Promise<SearchResult[]> {
    const response = await fetch(`/api/search?q=${query}`)
    const data = await response.json()
    return data.results
}
// Promise<T> = "这个函数返回的值，将来会是一个 T"

// void 返回（无返回值）
function log(message: string): void {
    console.log(message)
}

// never 返回（永远不返回，比如抛异常）
function fail(msg: string): never {
    throw new Error(msg)
}
```

### 数组返回类型

```typescript
function getNames(): string[] { return ["张三", "李四"] }
function getScores(): number[] { return [0.91, 0.74] }
function getEmpty(): string[] { return [] }

// 混合类型数组（可以，但不推荐）
function getMixed(): (string | number)[] {
    return ["张三", 25, "李四", 30]
}

// 对象数组（最常用）
function getDocs(): WikiDocument[] {
    return [
        { title: "IAP退款流程", type: "source", tags: ["支付"] },
        { title: "OpenAI", type: "entity", tags: ["公司"] },
    ]
}
```

---

## 1.7 解构赋值

### 对象基础解构

```typescript
const doc = {
    title: "IAP退款流程",
    type: "source",
    tags: ["支付", "流程"],
    wordCount: 3200,
}

const { title, type, tags, wordCount } = doc
// title = "IAP退款流程", type = "source", tags = ["支付", "流程"], wordCount = 3200
// 等价于：const title = doc.title; const type = doc.type; ...
```

### 重命名解构

```typescript
// 变量名冲突时需要重命名
function process(title: string, doc: WikiDocument) {
    const { title: docTitle } = doc   // 从 doc 中取出 title 并重命名为 docTitle
    console.log(title)     // 参数的 title
    console.log(docTitle)  // doc 内部的 title
}

// API 返回字段名和内部变量名不一致
const { data: { items: documents, total: totalCount } } = apiResponse
// items → 重命名为 documents，total → 重命名为 totalCount
```

### 默认值解构

```typescript
// 最常用于函数参数
function search(query: string, options?: SearchOptions) {
    const { topK = 5, mode = "hybrid" } = options ?? {}
    // options 是 undefined → ?? {} → 空对象 → 取默认值
}

// React 组件参数中大量使用
function SearchBar({
    placeholder = "搜索知识库...",
    onSearch,
    topK = 5,
}: SearchBarProps) {
    // 直接使用 placeholder、onSearch、topK
}
```

### 嵌套解构

```typescript
const doc = {
    title: "IAP退款流程",
    metadata: {
        source_file: "raw/payments/iap-refund.md",
        word_count: 3200,
    },
    chunks: [
        { id: "c1", content: "步骤一..." },
        { id: "c2", content: "步骤二..." },
    ],
}

const { metadata: { source_file, word_count } } = doc
// source_file = "raw/payments/iap-refund.md", word_count = 3200

// 嵌套 + 重命名 + 默认值 + 取数组第一项
const {
    metadata: {
        source_file: filePath,
        word_count: words = 0,
    },
    chunks: [firstChunk],
} = doc
```

### 数组解构

```typescript
const colors = ["red", "green", "blue", "yellow"]

const [first, second] = colors         // first = "red", second = "green"
const [, second] = colors               // 跳过第一个
const [first, ...rest] = colors         // first = "red", rest = ["green", "blue", "yellow"]

// swap
let a = 1, b = 2
;[a, b] = [b, a]    // a = 2, b = 1（和 Python 一样）

// React useState 返回值解构
const [query, setQuery] = useState("")
//        ↑          ↑
//   当前值      更新函数
```

### React 组件 Props 解构（项目中最高频）

```typescript
interface DocumentCardProps {
    doc: WikiDocument
    isActive: boolean
    onSelect: (docId: string) => void
    rank?: number
}

// 不解构（丑）
function DocumentCard(props: DocumentCardProps) {
    return <div onClick={() => props.onSelect(props.doc.title)}>{props.doc.title}</div>
}

// 解构（推荐，99% 的组件都这样写）
function DocumentCard({ doc, isActive, onSelect, rank }: DocumentCardProps) {
    return <div onClick={() => onSelect(doc.title)}>{doc.title}</div>
}

// 嵌套解构
function DocumentCard({ doc: { title, type, tags }, isActive, onSelect }: DocumentCardProps) {
    return <div onClick={() => onSelect(title)}>{title} - {type}</div>
}
```

---

## 1.8 箭头函数 vs 普通函数

语法对比：

```typescript
// 普通函数声明
function search(query: string): SearchResult[] {
    return [{ title: "测试", score: 0.9 }]
}

// 箭头函数（确实是 lambda！和 Python 的 lambda / Java 的 lambda 几乎一样）
const search = (query: string): SearchResult[] => {
    return [{ title: "测试", score: 0.9 }]
}

// 箭头函数单行简写（省略 return）
const double = (x: number) => x * 2
```

三个关键区别：

**区别 1：this 绑定（最关键）**

```typescript
class Timer {
    count = 0

    start() {
        // ❌ 普通 function：this 在 setInterval 里丢失
        // setInterval(function() { this.count++ }, 1000)    // this 不是 Timer

        // ✅ 箭头函数：this 继承外层（Timer 实例）
        setInterval(() => {
            this.count++     // this 是 Timer 实例，正确
        }, 1000)
    }
}
```

**区别 2：作为参数传递时的简洁度**

```typescript
const names = users.map(function(u) { return u.name })   // 普通：6 行
const names = users.map(u => u.name)                      // 箭头：1 行
```

**区别 3：不能 new**

```typescript
const Person = (name: string) => { this.name = name }
const p = new Person("张三")  // ❌ 箭头函数不能 new
```

项目经验法则：
- **用箭头函数**：回调、map/filter/reduce、React 组件内的事件处理
- **用普通函数**：导出的主要函数、组件定义
- **无所谓**：其余情况

---

## 1.9 类型断言 as

`as` 告诉编译器"我比你更了解这个类型"。不做运行时检查。

```typescript
// 典型场景：DOM 操作
const element = document.getElementById("search-input") as HTMLInputElement
// getElementById 返回 HTMLElement | null
// HTMLElement 没有 .value 属性，只有 HTMLInputElement 才有
// as 告诉编译器"我确定它是 input"
element.value = "hello"   // 编译通过

// ⚠️ 但不做运行时检查！如果元素不是 input → 运行时爆炸
// 更安全的写法：
const el = document.getElementById("search-input")
if (el instanceof HTMLInputElement) {
    el.value = "hello"   // 运行时真的检查
}

// 其他场景：
const data = JSON.parse('{"title":"测试"}') as WikiDocument  // JSON.parse 返回 any
const first = (result as string).toUpperCase()                 // 确定有值
```

```
as ≈ Java 的强制类型转换 (HTMLInputElement) el
Python 没有等价物（Python 本来就不做编译期检查）
```

---

## 1.10 联合类型 |

一个值可以是多种类型之一：

```typescript
// 字符串字面量联合（最常用，类似 enum）
type DocType = "source" | "entity" | "concept" | "synthesis"
const t: DocType = "source"     // ✅
const t: DocType = "article"    // ❌ "article" 不在联合中

// 类型联合
type Result = string | Error

// 联合类型数组
function getMixed(): (string | number)[] {
    return ["张三", 25]
}
```

类型收窄（Type Narrowing）——编译器根据条件自动缩小范围：

```typescript
function formatResult(result: Result): string {
    if (result instanceof Error) {
        return result.message        // 一定是 Error
    }
    return result.toUpperCase()      // 一定是 string
}

// typeof 收窄
function handle(value: string | number) {
    if (typeof value === "string") {
        return value.toUpperCase()
    }
    return value.toFixed(2)
}

// 判别联合类型（Discriminated Union）——项目中最常用
interface SourceDoc {
    type: "source"                // 标签字段
    source_file: string           // source 特有
}
interface EntityDoc {
    type: "entity"                // 标签字段
    sources: string[]             // entity 特有
}
type WikiDocument = SourceDoc | EntityDoc

function render(doc: WikiDocument) {
    if (doc.type === "source") {
        console.log(doc.source_file)   // ✅ TS 知道这是 SourceDoc
    } else {
        console.log(doc.sources)       // ✅ TS 知道这是 EntityDoc
    }
}
```

---

## 1.11 ?? 空值合并运算符

**`??` = 左边是 null 或 undefined → 返回右边；否则返回左边**

完整的 falsy 值体系（JavaScript 特有）：

```typescript
// JS 中只有 7 个 falsy 值：
false, 0, -0, 0n, "", null, undefined, NaN
// 其他所有值都是 truthy，包括 ""（空字符串以外）、[]（空数组）、{}（空对象）
```

`??` vs `||` 完整对比：

```typescript
const tests = [
    ["hello",  "default"],
    ["",       "default"],
    [0,        "default"],
    [false,    "default"],
    [null,     "default"],
    [undefined,"default"],
]

tests.forEach(([value, fallback]) => {
    console.log(`值: ${JSON.stringify(value)}`)
    console.log(`  ?? → ${value ?? fallback}`)    // 只替换 null/undefined
    console.log(`  || → ${value || fallback}`)    // 替换所有 falsy
})

// 结果：
// 值: "hello"      ?? → "hello"       || → "hello"
// 值: ""            ?? → ""            || → "default"    ← 差异！
// 值: 0             ?? → 0             || → "default"    ← 差异！
// 值: false         ?? → false          || → "default"    ← 差异！
// 值: null          ?? → "default"     || → "default"
// 值: undefined     ?? → "default"     || → "default"
```

```
经验法则：
  0 / "" / false 是合法值 → 用 ??
  0 / "" / false 应该被替换 → 用 ||
  不确定 → 用 ??（更安全，不会误杀合法值）

Python 的 or ≈ JS 的 ||
Python 没有 ?? 的精确等价物（需要 x if x is not None else default）
Java 没有直接等价物（Optional.ofNullable(x).orElse(default) 最接近）
```

---

## 1.12 类型推断的边界

小结：什么时候需要手写类型

```
✅ 不需要手写：                         ❌ 需要手写：
  const name = "张三"                      function greet(name: string)
  function add(a: number) {                const config: Config = {}
      return a + b                         const items: string[] = []
  const doc = { title: "测试", ... }       const doc: WikiDocument = { ... }
  const data = await res.json()            // 如果 res.json() 返回 any

好习惯（推荐但不强制）：
  函数返回复杂类型 → 写返回类型（自文档化）
  API 响应 → 写类型注解（有 interface 的话）
```

---

## 1.13 Python 的 TypedDict / dataclass / 纯 class — 和 TS interface 的关系

### 为什么要讲这个？

你在 1.5 节看到 TS interface 的定位是"描述数据形状"。Python 里也有类似的东西，而且更复杂——Python 有 **四种** 方式描述数据结构，每种的本质都不同。理解它们的区别，能帮你更深刻地理解 TS interface 在整个编程语言生态中的位置。

### Python 描述数据的四种方式

```python
# ── 方式 1：纯 dict（最原始）──
user = {"name": "张三", "age": 25}
user["naem"] = "李四"    # 拼写错误！Python 不报错，运行时才 KeyError
# 编辑器不提示有哪些 key，没有任何保护

# ── 方式 2：TypedDict（有类型提示的 dict）──
from typing import TypedDict

class UserInfo(TypedDict):
    name: str
    age: int

user: UserInfo = {"name": "张三", "age": 25}
user["naem"] = "李四"    # VS Code / mypy 立刻画红线！"naem" is not a valid key
# 但运行时仍然不检查！print(type(user))  → <class 'dict'>

# ── 方式 3：dataclass（带类型注解的类）──
from dataclasses import dataclass

@dataclass
class UserDC:
    name: str
    age: int

    def is_adult(self) -> bool:     # 可以定义方法！
        return self.age >= 18

user = UserDC(name="张三", age=25)
print(user.name)           # 用点号访问（不用 ["name"]）
user.naem = "李四"         # VS Code 画红线！
# 运行时是真正的对象：print(type(user))  → <class '__main__.UserDC'>

# ── 方式 4：纯 class（不装饰器）──
class UserPlain:
    name: str
    age: int = 18

user = UserPlain()
user.name = "张三"
# ① 没有自动 __init__，不能 UserPlain(name="张三")（要自己写构造函数）
# ② 是对象不是字典，不能 json.dumps(user)
# ③ 也可以定义方法
```

### TypedDict vs dict：核心区别

```
dict（普通字典）                    TypedDict（类型化字典）
─────────────────────────────────────────────────────────
本质     运行时的实体对象/数据结构      编译期/开发期的类型注解
键约束   动态，可以任意添加/删除键     静态的，结构在定义时就固定
代码提示 无（编辑器不知道有哪些键）    有（敲 user[" 自动弹出 name / age）
运行时   严格执行字典操作               退化为普通 dict，零性能开销
类型校验 无                             仅 mypy/pyright 检查，运行时不检查
```

TypedDict 运行时"隐形"的关键证据：

```python
from typing import TypedDict

class UserInfo(TypedDict):
    name: str
    age: int

user: UserInfo = {"name": "张三", "age": 25}
print(type(user))        # → <class 'dict'>      不是 UserInfo！
print(isinstance(user, UserInfo))  # → True          但只是类型标记

# 如果你通过网络请求拿到错误的 JSON：
bad_data = '{"name": "张三", "age": "二十五"}'    # age 应该是 int 不是 str
user: UserInfo = json.loads(bad_data)
# ✅ 不报错！TypedDict 运行时完全不检查类型
# 只有 mypy/pyright 在代码扫描时才会警告
```

### TypedDict vs dataclass：选哪个？

```
TypedDict                           dataclass
─────────────────────────────────────────────────────────
底层本质   纯 dict（键值对映射）         真正的 Python 类
访问方式   user["name"]（中括号）       user.name（点号）
能定义方法  ❌ 不能                      ✅ 可以
默认值     不支持复杂的默认值工厂        支持 field(default_factory=...)
JSON 序列化 json.dumps(user) 直接用    需要 asdict(user) 转换
运行时存在  弱（退化为 dict）            强（真正的对象，支持 isinstance）
```

```python
# 同样的数据，两种方式：

# TypedDict：适合"进来是 JSON，出去也是 JSON"的场景
from typing import TypedDict
class APIResponse(TypedDict):
    success: bool
    data: list
    error: str | None

resp: APIResponse = {"success": True, "data": [...], "error": None}
json.dumps(resp)      # ✅ 直接序列化

# dataclass：适合"数据 + 行为"的场景
@dataclass
class Order:
    items: list[str]
    total: float

    def can_refund(self) -> bool:    # 有方法
        return self.total < 10000

order = Order(items=["手机", "壳"], total=5999)
order.can_refund()    # ✅ 调用方法
json.dumps(asdict(order))  # 需要先转换
```

选择经验：
- **接口层 / JSON 数据传输** → TypedDict（进来是 JSON，出去也是 JSON）
- **领域模型 / 有业务逻辑** → dataclass（数据 + 行为绑定在一起）
- **轻量配置** → TypedDict（只要防拼写错误）

### 纯 class 为什么不够用？

```python
# Python 3.6+ 支持变量注解
class UserPlain:
    name: str            # 只是类型注解，没有赋值
    age: int = 18         # 既有类型注解，又有默认值

# 两个巨大痛点：

# 痛点 1：没有自动 __init__
# user = UserPlain(name="张三", age=25)   ❌ 报错！
# 因为纯类不会自动生成构造函数
user = UserPlain()
user.name = "张三"     # 只能这样，逐个赋值

# 痛点 2：不是字典
# json.dumps(user)   ❌ 报错！
# user["name"]        ❌ 报错！
# 只能用 user.name
```

这就是 dataclass 存在的意义——给纯 class 自动补上 `__init__`、`__repr__`、`__eq__` 等机械方法。

### 四种方式 + TS interface 的完整对照表

```
Python 纯 dict     → JS {}（无类型）
Python TypedDict    → TS interface（类型注解，运行时消失）
Python dataclass    → TS class（有行为、可实例化、运行时存在）
Python 纯 class     → TS class（有行为、可实例化、运行时存在）

但有一个重要区别：
  Python TypedDict 的类型检查 → 需要第三方工具 mypy/pyright
  TS interface 的类型检查   → 语言自带编译器 tsc（见 1.14 节）
```

---

## 1.14 TypeScript 的类型检查是真检查还是第三方工具

### 一句话回答

**TypeScript 的类型检查是由它自己的官方编译器（tsc）完成的，不是第三方工具。** 但它只在编译期检查，运行时类型全部消失。

### TS 代码的完整生命周期

```
[编写阶段] TypeScript 源码 (.ts)
       │
       ▼ (执行 tsc 编译)
[编译阶段] ① 真正的静态类型检查 → 类型有错，直接拦截，编译失败！
       │  ② 类型擦除（Erase Types）→ 把所有 interface/type/注解全部删除
       ▼
[运行阶段] 纯 JavaScript 代码 (.js) → 丢给浏览器或 Node.js 运行（此时完全没有类型）
```

```typescript
// 你写的 TS：
const age: number = 25
const doc: WikiDocument = { title: "测试", type: "source", tags: [] }
interface WikiDocument { title: string; type: string; tags: string[] }

// 编译后的 JS（所有类型都没了）：
const age = 25
const doc = { title: "测试", type: "source", tags: [] }
// interface 完全消失！
```

### 它算"借助第三方工具"吗？

```
Python 的情况（借助第三方）：
  Python 语言官方解释器（CPython）不管类型
  类型注解在标准 Python 里纯粹是"摆设"
  需要 mypy / pyright / Pylance 等第三方工具做检查
  不用这些工具 → 类型注解被完全忽略，代码照常运行

TypeScript 的情况（官方原生）：
  tsc 编译器就是 TypeScript 语言的核心
  装了 TypeScript 就自带类型检查器
  VS Code 内置的 TS 检查引擎是微软官方直接把 tsc 集成进去的
  类型检查是语言自身的本职工作，不是外挂
  不通过类型检查 → 代码编译失败 → 无法部署
```

### Python vs TypeScript vs Java 的"类型严格度"光谱

```
                编译期严格度                    运行时严格度
                ────────────                    ────────────
Python          第三方工具（可选）               完全没有
(mypy/pyright)   不用也能跑                      动态语言，无类型约束

TypeScript      官方编译器 tsc（强制）           完全没有
                编译失败就无法发布               运行时变成纯 JS

Java            官方编译器 javac（强制）          有
                编译失败就无法运行               运行时仍有类型约束
                                               （如 ClassCastException）
```

```
Python：  开发期靠自觉（mypy），运行期裸奔
TypeScript：开发期有编译器强制把关，运行期裸奔
Java：     开发期编译器强制把关，运行期仍有保护
```

### 这意味着什么？

```typescript
// 编译期（tsc 检查）—— 严格的
const doc: WikiDocument = { title: "测试", type: 123, tags: [] }
//                                              ^^^
// ❌ 编译报错：Type 'number' is not assignable to type 'string'
// 代码根本编译不过，无法部署

// 但编译后变成 JS（运行期）—— 完全没有检查
// JS 代码：
var doc = { title: "测试", type: 123, tags: [] }
// 这段 JS 在浏览器里运行完全没问题
// 123 就是 123，JS 不在乎它"应该"是什么类型

// 所以如果你绕过 tsc（比如用 any 或者强制编译），运行时没有类型保护
const doc: any = { title: "测试", type: 123, tags: [] }
// any 逃逸了类型检查 → 编译通过 → 运行时 type 是 123，没人在乎
```

### 对你项目的影响

```
你的工作流：
  写代码 → VS Code 实时检查（tsc 驱动）→ 保存时发现错误 → 修改 → 通过检查 → 提交

只要你不：
  - 用 any 逃逸类型检查
  - 用 // @ts-ignore 强制跳过
  - 绕过 tsc 直接运行 .ts 文件

类型检查就是"真的"——在工程管线中作为构建前置条件，类型报错就无法发布上线。

但它的一生是孤独的：所有严格和安全都留在编译阶段；到了运行阶段，它脱下类型铠甲，裸奔在 JavaScript 世界里。
```

---

# 第二部分：框架基础

## 2.1 JSX / TSX 是什么

JSX 是 JavaScript 的语法扩展，让你在 JS 里写"看起来像 HTML"的代码。但它不是 HTML，是编译成函数调用的语法糖。

```typescript
// 你写的 JSX：
const element = <h1 className="title">Hello, {name}!</h1>

// 编译后的 JS（React.createElement 调用）：
const element = React.createElement("h1", { className: "title" }, "Hello, ", name, "!")
```

JSX vs HTML 关键差异：

```typescript
// ① class → className（class 是 JS 保留字）
<div className="container">     // ✅
<div class="container">          // ❌

// ② for → htmlFor
<label htmlFor="search-input">搜索</label>

// ③ 自闭合标签必须有 /
<img src="logo.png" />     // ✅
<img src="logo.png">        // ❌

// ④ style 必须是对象（注意双大括号）
<div style={{ color: "red", fontSize: 16 }}>     // ✅
<div style="color: red">                           // ❌

// ⑤ 事件名 camelCase
onClick onChange onKeyDown onSubmit

// ⑥ 注释
{/* JSX 注释 */}

// ⑦ 只能有一个根元素（或 Fragment <>）
<>
    <h1>Title</h1>
    <p>Content</p>
</>
```

文件扩展名：
- `.js` — 纯 JavaScript
- `.ts` — TypeScript
- `.jsx` — JavaScript + JSX
- `.tsx` — TypeScript + JSX（你项目中全用这个）

---

## 2.2 React vs Next.js

层级关系：

```
JavaScript (语言，1995)
└── TypeScript (超集，2012，JS + 静态类型)
    ├── .js 文件
    └── .ts / .tsx 文件

├── React (UI 库)          ← 用 JSX 构建 UI，只管"怎么画界面"
│   └── Next.js (框架)     ← 基于 React，加上了路由 + API + SSR + 打包

Python 类比：
  React ≈ Flask（微型，只管核心）
  Next.js ≈ Django（全家桶，开箱即用）
  Vue ≈ React（同一级别）
```

React vs Next.js 的区别：

```typescript
// React：需要自己搭路由、数据获取、后端、构建
import { BrowserRouter, Routes, Route } from "react-router-dom"
function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/chat" element={<Chat />} />
            </Routes>
        </BrowserRouter>
    )
}

// Next.js：文件路由，零配置
// app/page.tsx          → / 路由自动生成
// app/chat/page.tsx     → /chat 路由自动生成
// 不需要手写路由配置
```

```
React 只解决一个事：怎么画 UI
你需要自己选：路由库、状态管理、构建工具、后端框架

Next.js 是基于 React 的完整框架：
  路由 → 文件系统路由（app/chat/page.tsx → /chat）
  数据获取 → Server Component 里直接 await
  后端 API → API Routes（app/api/search/route.ts）
  构建 → 零配置（next build）
```

---

## 2.3 Server Component vs Client Component

### 核心区别

```
Server Component（默认，不需要标记）：
  代码在服务器执行 → HTML 在服务器生成后发给浏览器
  ✅ 可以直接访问数据库、文件系统
  ❌ 不能用 useState、useEffect、onClick
  1 次网络往返就返回完整内容

Client Component（需要 "use client"）：
  代码在浏览器执行 → JS 下载到用户电脑上运行
  ✅ 可以用 useState、useEffect、所有事件处理
  ❌ 不能直接访问数据库
  需要下载 JS + 再次请求数据（至少 2 次网络往返）
```

### Server Component 网络交互

```
浏览器                            Next.js 服务器              数据库
  │                                  │                       │
  │── GET /documents ──────────→    │                       │
  │                                  │── SELECT * ────────→  │
  │                                  │←── [{IAP,...}] ─────│
  │                                  │                       │
  │                                  │  服务器执行组件：      │
  │                                  │  渲染成完整 HTML      │
  │                                  │                       │
  │←── 完整 HTML（已有内容）──│                       │
  │                                  │                       │
  浏览器直接显示，没有额外 JS         │                       │
  总共 1 次网络往返
```

### Client Component 网络交互

```
浏览器                            Next.js 服务器
  │                                  │
  │── GET /search ──────────→      │
  │←── HTML 壳 + JS 包 ──────────│    （第 1 次往返）
  │                                  │
  浏览器下载 JS → 执行 → 显示空页面   │
  用户输入 "IAP退款" → 点击搜索      │
  │                                  │
  │── GET /api/search?q=IAP退款 →│    （第 2 次往返）
  │←── JSON {results:[...]} ───│
  │                                  │
  JS 接收数据 → React 重新渲染      │
  用户终于看到搜索结果
```

### 简单规则

```
需要用户交互（点击、输入、hover）？ → "use client"
需要 useState / useEffect？           → "use client"
只是展示数据？                        → Server Component（默认）
需要访问数据库/文件系统？              → Server Component
```

### 混合使用

```typescript
// app/documents/page.tsx — Server Component
export default async function DocumentsPage() {
    const docs = await db.getDocuments()    // 服务器查数据库

    return (
        <div>
            <h1>文档管理</h1>
            <SearchFilter onFilter={handleSearch} />    {/* Client Component */}
            <ul>
                {docs.map(doc => <li key={doc.id}>{doc.title}</li>)}    {/* Server 渲染 */}
            </ul>
        </div>
    )
}

// components/SearchFilter.tsx — Client Component
"use client"
export function SearchFilter({ onFilter }: Props) {
    const [selected, setSelected] = useState("all")    // 需要 useState
    return (
        <div>
            {types.map(type => (
                <button key={type} onClick={() => setSelected(type)}>{type}</button>
            ))}
        </div>
    )
}
```

---

## 2.4 Next.js API Routes

Next.js 内置了 API 功能，不需要 Express：

```typescript
// app/api/search/route.ts
import { NextRequest, NextResponse } from "next/server"

// GET /api/search?q=xxx&mode=hybrid&topK=5
export async function GET(request: NextRequest) {
    const { searchParams } = request.nextUrl
    const query = searchParams.get("q") ?? ""
    const mode = searchParams.get("mode") ?? "hybrid"
    const topK = parseInt(searchParams.get("topK") ?? "5")

    const results = await searchService.hybridSearch(query, mode, topK)

    return NextResponse.json({
        success: true,
        data: results,
        total: results.length,
    })
}

// POST /api/documents
export async function POST(request: NextRequest) {
    const body = await request.json()
    const doc = await documentService.create(body)
    return NextResponse.json({ success: true, data: doc })
}
```

项目目录结构：

```
src/
├── app/                    ← 路由根目录
│   ├── layout.tsx          ← 根布局（≈ Vue 的 App.vue）
│   ├── page.tsx            ← 首页 /
│   ├── chat/page.tsx       ← /chat 路由
│   ├── documents/page.tsx  ← /documents 路由
│   ├── search/page.tsx     ← /search 路由
│   └── api/                ← API 路由（后端）
│       ├── search/route.ts    ← GET /api/search
│       └── documents/route.ts ← GET/POST /api/documents
├── components/             ← 可复用组件
├── lib/                    ← 工具函数
├── types/                  ← TypeScript 类型定义
└── styles/                 ← 全局样式
```

路由规则：文件路径 = URL 路径。`app/chat/page.tsx` = `/chat`。

---

## 2.5 SEO 是什么

**SEO = Search Engine Optimization = 让搜索引擎（Google/Baidu）能理解你的网页内容。**

三种渲染模式对比：

```
传统服务端渲染（Django/JSP/PHP）：
  服务器生成完整 HTML → 发给浏览器
  Googlebot 和用户看到的一样 ✅ SEO 友好

纯客户端渲染（React SPA / Vue SPA）：
  服务器返回空壳 <div id="root"></div> + JS
  内容是 JS 在浏览器里渲染的
  Googlebot 可能看到空白页 ❌ SEO 不友好

Next.js Server Component（SSR）：
  服务器执行组件 → 生成完整 HTML → 发给浏览器
  Googlebot 看到完整内容 ✅ SEO 友好
```

**对你项目的影响**：知识库是 Tauri 桌面客户端，没有公网 URL，SEO 不重要。但 Server Component 仍然有用——减少 JS 体积、首次渲染更快、数据安全。

---

## 2.6 Express 是什么

Express = Node.js 最流行的 Web 框架（≈ Python 的 Flask / Java 的 Spring Boot）

```javascript
// Express 写法
import express from "express"
const app = express()

app.get("/api/search", (req, res) => {
    const query = req.query.q
    res.json({ results: [] })
})

app.listen(8000)
```

Next.js 不需要 Express，因为内置了 API Routes（见 2.4）。

```
对比：
  Express                          Next.js
─────────────────────────────────────────
  app.get("/api/search", ...)     文件 app/api/search/route.ts
  req.query.q                     request.nextUrl.searchParams.get("q")
  req.body                         request.json()
  res.json()                      NextResponse.json()
  app.listen(8000)                next dev（自动启动）
  需要 cors 中间件                不需要（同源）
  需要 @types/express            内置 TypeScript
```

---

## 2.7 Tree-shaking 与 import type

**Tree-shaking = 打包工具自动删除未使用的代码。**

原理：
1. 打包工具分析 `import/export` 关系，画出依赖图
2. 找出哪些函数被 import 且实际使用
3. 删除没被使用的代码

```typescript
// utils.ts
export function searchDocs(query: string) { /* ... */ }
export function formatTitle(title: string) { /* ... */ }
export function chunkText(text: string) { /* ... */ }

// page.tsx
import { searchDocs, formatTitle } from "./utils"
// 只 import 了 2 个 → chunkText 不打包 ✅
```

**`import type` 的作用**：明确告诉打包工具"这只是类型，编译后不存在"。

```typescript
// 普通导入
import { WikiDocument, searchDocs } from "./types"
// searchDocs 是函数 → 保留
// WikiDocument 是 interface → 编译后消失，但 import 让打包工具保留对文件的引用

// 类型导入
import type { WikiDocument } from "./types"
// 打包工具直接忽略这行，不分析这个依赖

// 同一文件混合导入
import { searchDocs } from "./types"
import type { WikiDocument } from "./types"
// 或简写：
import { searchDocs, type WikiDocument } from "./types"
```

经验法则：如果只导入类型 → 用 `import type`。

---

## 2.8 ES6 模块系统

```typescript
// 导出
// types.ts
export interface WikiDocument { title: string; type: DocType }
export type DocType = "source" | "entity" | "concept" | "synthesis"
export function formatDate(date: string): string { /* ... */ }
export default WikiDocument  // 默认导出（一个文件只能有一个）

// 导入
import WikiDocument, { DocType, formatDate } from "./types"     // 默认 + 具名
import { useState, useEffect } from "react"                       // 从 npm 包
import type { WikiDocument } from "./types"                     // 仅导入类型
```

---

# 第三部分：项目高频代码模式

```typescript
// ① 从 URL 获取参数
const params = request.nextUrl.searchParams
const query = params.get("q") ?? ""

// ② JSON 响应
return NextResponse.json({ success: true, data: results })

// ③ 受控输入框（v-model 替代品）
<input value={query} onChange={e => setQuery(e.target.value)} />

// ④ 条件渲染（v-if 替代品）
{loading ? <Spinner /> : <ResultList items={results} />}

// ⑤ 列表渲染（v-for 替代品）
{docs.map(doc => <DocCard key={doc.title} doc={doc} />)}

// ⑥ 空值安全链式调用
const score = doc?.metadata?.score ?? 0

// ⑦ useEffect 副作用（定时器、事件监听器）
useEffect(() => {
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)  // 清理函数（重要！）
}, [])

// ⑧ 动态 className（v-bind:class 替代品）
className={`card ${isActive ? "card--active" : ""}`}

// ⑨ props 展开传递
<Component {...commonProps} title="特殊标题" />

// ⑩ async/await + try/catch
try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
} catch (err) {
    console.error("搜索失败:", err)
    return []
}
```

---

# 第四部分：学习路线与资源

## 学习路线（最速路径）

```
Day 1: TypeScript 基础
  → 读阮一峰 TS 教程前 5 章（类型声明、接口、函数、类）
  → 在 TS Playground 里把上面代码跑一遍

Day 2: React 核心思维（从 Vue 转换）
  → 读 react.dev 的 "Quick Start" + "Describing the UI"
  → 重点理解：组件 = 函数、JSX 语法、useState/useEffect

Day 3: Next.js 约定
  → 跟着官方教程走一遍（约 2 小时）
  → 重点理解：文件路由、Server vs Client、API Routes

Day 4+: 开始项目 Phase 1（边做边学最快）
```

## 优质学习资源

### TypeScript

| 资源 | 说明 |
|---|---|
| [TypeScript 官方手册](https://www.typescriptlang.org/docs/) | 权威，有 Java 背景直接看这个 |
| [TypeScript 入门教程 - 阮一峰](https://wangdoc.com/typescript/) | 中文，覆盖面全，适合速查 |
| [TS Playground](https://www.typescriptlang.org/play) | 在线沙盒，随时验证语法 |

### Next.js

| 资源 | 说明 |
|---|---|
| [Next.js 官方教程](https://nextjs.org/learn) | 跟着做一遍，最快上手 |
| [Next.js App Router 文档](https://nextjs.org/docs/app) | 你项目用 App Router，直接看这个 |

### React（Vue 开发者补充）

| 资源 | 说明 |
|---|---|
| [React 官方 Quick Start](https://react.dev/learn) | 只看 "Describing the UI" + "Adding Interactivity" |
| [React - Vue 开发者的 React 指南](https://react.dev/learn/thinking-in-react) | 给有其他框架经验的人写的 |

### 速查

| 资源 | 说明 |
|---|---|
| [React + TypeScript Cheatsheet](https://react.dev/learn/typescript) | 项目中最常翻的 |
| [JavaScript.info](https://javascript.info/) | JS 基础有疑问时查 |

---

# 附录：关键概念速查表

```
┌────────────┬───────────────────────────────────────────────────────────┐
│ 概念        │ 一句话解释                                                │
├────────────┼───────────────────────────────────────────────────────────┤
│ TS 类型推断 │ 不用手写类型，编译器从值自动推断                           │
│ 可选属性 ?  │ 属性可以不存在，值是 T | undefined                          │
│ const      │ 声明常量变量（有值，运行时存在）≈ Java final               │
│ let        │ 声明可变变量（有值，运行时存在）                            │
│ type       │ 定义类型别名（无值，编译后消失）                           │
│ interface  │ 描述数据形状（无值，编译后消失）≈ Python TypedDict / dataclass  │
│ TypedDict   │ Python 的类型化字典（≈ TS interface，但类型检查靠 mypy）       │
│ dataclass   │ Python 的数据类（≈ TS class，运行时是真正的对象）                │
│ tsc         │ TS 官方编译器，做真正的类型检查，不是第三方工具                    │
│ class      │ 定义有行为的类（有值，运行时存在）≈ Java class             │
│ 联合类型    │ 值可能是多种类型之一：A | B | C                            │
│ as         │ 类型断言："我比编译器更了解这个类型" ≈ Java 强制转换         │
│ ??         │ 空值合并：左边 null/undefined → 返回右边 ≈ Optional.orElse │
│ ?.         │ 可选链：左边 null/undefined → 不报错，返回 undefined        │
│ 箭头函数    │ Lambda 表达式，this 绑定外层 ≈ Python lambda              │
│ 解构赋值    │ const { a, b } = obj — 从对象中提取属性 ≈ Python 解包     │
│ JSX        │ 在 JS 中写 HTML 标签的语法扩展                            │
│ .tsx       │ TypeScript + JSX 文件                                     │
│ React      │ UI 库（管怎么画界面）≈ Flask / Vue                        │
│ Next.js    │ 基于 React 的全栈框架（路由+API+SSR+构建）≈ Django        │
│ Server     │ 代码在服务器执行，能访问数据库，不能有交互                 │
│ Client     │ 代码在浏览器执行，能交互，不能直接访问数据库               │
│ SEO        │ 搜索引擎优化，让 Google 能索引你的页面                     │
│ Express    │ Node.js 的 Web 框架（≈ Flask）                             │
│ Tree-shaking│ 打包时自动删除未使用的代码                                 │
│ import type│ 仅导入类型，不导入值，帮助打包工具优化                     │
└────────────┴──────────────────────────────────────────────────────────┘
```

---

*本文档基于 llm-wiki-agent 项目（PRD v2.9）的技术选型编写。*
*目标读者：具备 Python + Java + Vue 基础，需要快速上手 TypeScript 和 Next.js 的开发者。*
