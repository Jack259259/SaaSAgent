# assets/sops — SOP 库(当代码管理,入 git 走评审)

schema 见方案附录 B 与 `contracts/sop/_schema.yaml`(阶段 1)。任何改动必须通过
`make sop-validate` + 回放回归后才可合并(红线 10);执行器实现见阶段 8。
