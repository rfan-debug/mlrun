import typing

import mergedeep
import sqlalchemy.orm

import mlrun.api.schemas
import mlrun.api.utils.projects.remotes.follower
import mlrun.errors


class Member(mlrun.api.utils.projects.remotes.follower.Member):
    def __init__(self) -> None:
        super().__init__()
        self._projects: typing.Dict[str, mlrun.api.schemas.Project] = {}

    def create_project(
        self, session: sqlalchemy.orm.Session, project: mlrun.api.schemas.Project
    ):
        if project.metadata.name in self._projects:
            raise mlrun.errors.MLRunConflictError("Project already exists")
        self._projects[project.metadata.name] = project

    def store_project(
        self,
        session: sqlalchemy.orm.Session,
        name: str,
        project: mlrun.api.schemas.Project,
    ):
        self._projects[name] = project

    def patch_project(
        self,
        session: sqlalchemy.orm.Session,
        name: str,
        project: dict,
        patch_mode: mlrun.api.schemas.PatchMode = mlrun.api.schemas.PatchMode.replace,
    ):
        existing_project_dict = self._projects[name].dict()
        strategy = patch_mode.to_mergedeep_strategy()
        mergedeep.merge(existing_project_dict, project, strategy=strategy)
        self._projects[name] = mlrun.api.schemas.Project(**existing_project_dict)

    def delete_project(
        self,
        session: sqlalchemy.orm.Session,
        name: str,
        deletion_strategy: mlrun.api.schemas.DeletionStrategy = mlrun.api.schemas.DeletionStrategy.default(),
    ):
        if name in self._projects:
            del self._projects[name]

    def get_project(
        self, session: sqlalchemy.orm.Session, name: str
    ) -> mlrun.api.schemas.Project:
        return self._projects[name]

    def list_projects(
        self,
        session: sqlalchemy.orm.Session,
        owner: str = None,
        format_: mlrun.api.schemas.ProjectsFormat = mlrun.api.schemas.ProjectsFormat.full,
        labels: typing.List[str] = None,
        state: mlrun.api.schemas.ProjectState = None,
        names: typing.Optional[typing.List[str]] = None,
    ) -> mlrun.api.schemas.ProjectsOutput:
        if owner or labels or state:
            raise NotImplementedError(
                "Filtering by owner, labels or state is not supported"
            )
        projects = list(self._projects.values())
        if names:
            projects = [
                project
                for project_name, project in self._projects.items()
                if project_name in names
            ]
        if format_ == mlrun.api.schemas.ProjectsFormat.full:
            return mlrun.api.schemas.ProjectsOutput(projects=projects)
        elif format_ == mlrun.api.schemas.ProjectsFormat.name_only:
            project_names = [project.metadata.name for project in projects]
            return mlrun.api.schemas.ProjectsOutput(projects=project_names)
        else:
            raise NotImplementedError(
                f"Provided format is not supported. format={format_}"
            )
