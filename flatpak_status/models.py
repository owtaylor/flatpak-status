from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import as_declarative
from sqlalchemy.orm import joinedload, object_session, relationship


@as_declarative()
class Base:
    id = Column(Integer, primary_key=True)


# Package in Koji terms, but Package/Module/Flatpak
class KojiEntity:
    name = Column(String, index=True)
    koji_package_id = Column(Integer, nullable=False)

    @classmethod
    def get_for_name(cls, session, name, package_id=None, koji_session=None):
        if koji_session is None and package_id is None:
            raise RuntimeError("Either package_id or koji_session must be specified")

        entity = session.query(cls).filter_by(name=name).first()
        if entity is None:
            if package_id is None:
                package_id = koji_session.getPackageID(name)
            entity = cls(name=name, koji_package_id=package_id)
            session.add(entity)

        return entity


class KojiBuild:
    koji_build_id = Column(Integer, nullable=False, index=True)
    nvr = Column(String, nullable=False, index=True)
    source = Column(String)
    completion_time = Column(DateTime)


class Flatpak(Base, KojiEntity):
    __tablename__ = 'flatpaks'

    koji_type = 'image'

    def __repr__(self):
        return f"<Flatpak(name={self.name})>"


class FlatpakBuild(Base, KojiBuild):
    __tablename__ = 'flatpak_builds'

    entity_id = Column(Integer, ForeignKey('flatpaks.id'))
    entity = relationship("Flatpak", back_populates="builds")

    def list_package_builds(self):
        """Gets package_builds with eager loading of package details"""
        return object_session(self).query(FlatpakBuildPackageBuild) \
                                   .filter_by(flatpak_build=self) \
                                   .options(joinedload(FlatpakBuildPackageBuild.package_build)
                                            .joinedload(PackageBuild.entity))

    def __repr__(self):
        return f"<FlatpakBuild(nvr={self.nvr})>"


Flatpak.builds = relationship("FlatpakBuild", back_populates="entity")


class FlatpakBuildPackageBuild(Base):
    __tablename__ = 'flatpak_build_package_builds'

    flatpak_build_id = Column(Integer, ForeignKey('flatpak_builds.id'))
    flatpak_build = relationship("FlatpakBuild", back_populates="package_builds")

    package_build_id = Column(Integer, ForeignKey('package_builds.id'))
    package_build = relationship("PackageBuild")


# We have an explicit function that does eager loading
FlatpakBuild.package_builds = relationship("FlatpakBuildPackageBuild",
                                           back_populates="flatpak_build")


class FlatpakBuildModuleBuild(Base):
    __tablename__ = 'flatpak_build_module_builds'

    flatpak_build_id = Column(Integer, ForeignKey('flatpak_builds.id'))
    flatpak_build = relationship("FlatpakBuild", back_populates="module_builds")

    module_build_id = Column(Integer, ForeignKey('module_builds.id'))
    module_build = relationship("ModuleBuild")


FlatpakBuild.module_builds = relationship("FlatpakBuildModuleBuild", back_populates="flatpak_build")


class Module(Base, KojiEntity):
    __tablename__ = 'modules'

    koji_type = 'module'

    def __repr__(self):
        return f"<Module(name={self.name})>"


class ModuleBuild(Base, KojiBuild):
    __tablename__ = 'module_builds'

    entity_id = Column(Integer, ForeignKey('modules.id'))
    entity = relationship("Module", back_populates="builds")

    flatpak = relationship("Module", back_populates="builds")

    def __repr__(self):
        return f"<Module(name={self.name})>"


Module.builds = relationship("ModuleBuild", back_populates="entity")


class ModuleBuildPackageBuild(Base):
    __tablename__ = 'module_build_package_builds'

    module_build_id = Column(Integer, ForeignKey('module_builds.id'))
    module_build = relationship("ModuleBuild", back_populates="package_builds")

    package_build_id = Column(Integer, ForeignKey('package_builds.id'))
    package_build = relationship("PackageBuild")


ModuleBuild.package_builds = relationship("ModuleBuildPackageBuild", back_populates="module_build")


class Package(Base, KojiEntity):
    __tablename__ = 'packages'

    koji_type = 'rpm'

    def __repr__(self):
        return f"<Package(name={self.name})>"


class PackageBuild(Base, KojiBuild):
    __tablename__ = 'package_builds'

    entity_id = Column(Integer, ForeignKey('packages.id'))
    entity = relationship("Package", back_populates="builds")

    package = relationship("Package", back_populates="builds")

    def __repr__(self):
        return f"<PackageBuild(nvr={self.nvr})>"


Package.builds = relationship("PackageBuild", back_populates="entity")


class BodhiUpdate:
    bodhi_update_id = Column(String)
    release_name = Column(String, index=True)
    release_branch = Column(String, index=True)
    status = Column(String)


class PackageUpdate(Base, BodhiUpdate):
    __tablename__ = 'package_updates'


class PackageUpdateBuild(Base):
    __tablename__ = 'package_update_builds'

    update_id = Column(Integer, ForeignKey('package_updates.id'))
    update = relationship("PackageUpdate", back_populates="builds")

    build_nvr = Column(String, nullable=False)
    entity_name = Column(String, nullable=False, index=True)


PackageUpdate.builds = relationship("PackageUpdateBuild", back_populates="update")


class FlatpakUpdate(Base, BodhiUpdate):
    __tablename__ = 'flatpak_updates'


class FlatpakUpdateBuild(Base):
    __tablename__ = 'flatpak_update_builds'

    update_id = Column(Integer, ForeignKey('flatpak_updates.id'))
    update = relationship("FlatpakUpdate", back_populates="builds")

    build_nvr = Column(String, nullable=False)
    entity_name = Column(String, nullable=False, index=True)


FlatpakUpdate.builds = relationship("FlatpakUpdateBuild", back_populates="update")


class BuildCacheItem(Base):
    __tablename__ = 'build_cache_items'

    package_name = Column(String, nullable=False)
    koji_type = Column(String, nullable=False)
    last_queried = Column(DateTime)


class UpdateCacheItem(Base):
    __tablename__ = 'update_cache_items'

    content_type = Column(String, nullable=False)
    package_name = Column(String, nullable=False)
    last_queried = Column(DateTime)
